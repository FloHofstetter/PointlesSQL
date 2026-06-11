"""Genie-space business logic — curation, prompt context, SQL generation.

Storage-shaped CRUD mirrors :mod:`pointlessql.services.bi_dashboards`
(detached rows, owner + admin mutate, slugified titles).  The two
LLM-facing helpers are deliberately thin reuses of the Lens plumbing:

* :func:`build_context` renders the space's curated tables (compact
  DDL from the UC facade), metric views (dimensions / measures),
  curator instructions, and trusted Q→SQL examples into one capped
  prompt block.
* :func:`generate_sql` resolves the workspace's BYO Lens credential
  (:mod:`pointlessql.services.lens._provider_creds`), builds the
  provider adapter via
  :func:`pointlessql.services.lens.llm_provider.get_provider`, and
  runs one ``chat_with_tools`` round-trip with a SQL-only system
  prompt.  No new provider client is introduced.

Validation is defence in depth: :func:`validate_generated_sql`
re-parses the model output with :func:`pointlessql.pql.prepare_sql`
(single SELECT only) and rejects any table reference outside the
space's curated list — the per-user SELECT privilege check in the
route layer still applies on top.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.models.genie import (
    GenieMessage,
    GenieSpace,
)
from pointlessql.pql import prepare_sql
from pointlessql.types import ErrorCode

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.config import Settings

from pointlessql.services.genie._crud import (
    list_trusted_assets,
    space_metric_views,
    space_tables,
)

_UNSET: Any = object()
"""Sentinel distinguishing "leave unchanged" from "set to None"."""

_FQN_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
"""Three-part ``catalog.schema.table`` shape for curated entries."""

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
"""First fenced code block in an LLM reply (``sql`` tag optional)."""

CONTEXT_CHAR_CAP = 8_000
"""Hard cap on the rendered prompt context."""

_TABLE_BLOCK_CHAR_CAP = 1_200
"""Per-table soft cap — long column lists truncate gracefully."""

MAX_TRUSTED_EXAMPLES = 8
"""How many trusted Q→SQL pairs ship as few-shot examples."""

GENIE_SYSTEM_PROMPT = (
    "You translate questions into a single DuckDB SELECT over the "
    "given tables.  Use only the tables listed in the context, always "
    "with their full three-part catalog.schema.table names.  Answer "
    "ONLY with SQL in a ```sql block or raw — no prose, no "
    "explanation, no DDL/DML."
)
"""System prompt anchoring the SQL-only contract."""


class GenieLLMNotConfiguredError(PointlessSQLError):
    """Raised when the workspace has no enabled LLM credential.

    Mirrors the Lens gate
    (:class:`pointlessql.services.lens._chat_loop.LensProviderNotConfiguredError`)
    but answers 503 — the room is configured correctly, the install
    is just missing its BYO key, which is an operator concern rather
    than a caller mistake.

    Attributes:
        status_code: Always 503.
        error_code: Always :data:`ErrorCode.GENIE_LLM_NOT_CONFIGURED`.
    """

    status_code: int = 503
    error_code: ErrorCode = ErrorCode.GENIE_LLM_NOT_CONFIGURED


def _render_table_block(full_name: str, info: dict[str, Any]) -> str:
    """Render one curated table as a compact DDL-ish prompt block."""
    lines: list[str] = []
    comment = str(info.get("comment") or "").strip()
    header = f"TABLE {full_name}"
    if comment:
        header += f" -- {comment}"
    lines.append(header)
    columns = cast("list[dict[str, Any]]", info.get("columns") or [])
    rendered_chars = len(header)
    for idx, col in enumerate(columns):
        col_name = str(col.get("name") or "")
        col_type = str(col.get("type_text") or col.get("type_name") or "")
        col_line = f"  {col_name} {col_type}".rstrip()
        col_comment = str(col.get("comment") or "").strip()
        if col_comment:
            col_line += f" -- {col_comment}"
        lines.append(col_line)
        rendered_chars += len(col_line) + 1
        if rendered_chars > _TABLE_BLOCK_CHAR_CAP:
            remaining = len(columns) - idx - 1
            if remaining > 0:
                lines.append(f"  ... (+{remaining} more columns)")
            break
    return "\n".join(lines)


def _render_metric_view_block(full_name: str, info: dict[str, Any]) -> str:
    """Render one metric view's dimensions / measures for the prompt."""
    lines = [f"METRIC VIEW {full_name} (source: {info.get('source_table_full_name') or '?'})"]
    comment = str(info.get("comment") or "").strip()
    if comment:
        lines[0] += f" -- {comment}"
    spec = cast("dict[str, Any]", info.get("spec") or {})
    for kind in ("dimensions", "measures"):
        for entry in cast("list[dict[str, Any]]", spec.get(kind) or []):
            lines.append(f"  {kind[:-1]} {entry.get('name')}: {entry.get('expr')}")
    spec_filter = str(spec.get("filter") or "").strip()
    if spec_filter:
        lines.append(f"  filter: {spec_filter}")
    return "\n".join(lines)


async def build_context(
    uc_client: Any,
    factory: sessionmaker[Session],
    space: GenieSpace,
) -> str:
    """Render the space's curated scope into one LLM prompt block.

    Curated tables come back from the UC facade as compact DDL
    (name, columns with type + comment, table comment); metric views
    contribute their dimension / measure expressions; curator
    instructions and up to :data:`MAX_TRUSTED_EXAMPLES` trusted
    Q→SQL pairs close the block.  A table or metric view the catalog
    no longer knows is skipped rather than failing the whole ask.

    Args:
        uc_client: A :class:`UnityCatalogClient` facade instance.
        factory: SQLAlchemy session factory (for trusted assets).
        space: The detached space row.

    Returns:
        The rendered context, capped at
        :data:`CONTEXT_CHAR_CAP` characters (truncated per-table
        first, then hard-cut with a marker).
    """
    sections: list[str] = ["You may query ONLY these tables:"]
    for full_name in space_tables(space):
        parts = full_name.split(".")
        if len(parts) != 3:
            continue
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            continue
        sections.append(_render_table_block(full_name, cast("dict[str, Any]", info)))

    metric_blocks: list[str] = []
    for full_name in space_metric_views(space):
        info = await uc_client.get_metric_view(full_name)
        if not info:
            continue
        metric_blocks.append(_render_metric_view_block(full_name, cast("dict[str, Any]", info)))
    if metric_blocks:
        sections.append("Semantic-layer definitions (use their expressions over the source):")
        sections.extend(metric_blocks)

    instructions = (space.instructions or "").strip()
    if instructions:
        sections.append(f"Curator instructions:\n{instructions}")

    assets = list_trusted_assets(factory, space_id=space.id)[:MAX_TRUSTED_EXAMPLES]
    if assets:
        sections.append("Trusted examples:")
        for asset in assets:
            sections.append(f"Q: {asset.question}\nSQL: {asset.sql_text}")

    context = "\n\n".join(sections)
    if len(context) > CONTEXT_CHAR_CAP:
        marker = "\n... (context truncated)"
        context = context[: CONTEXT_CHAR_CAP - len(marker)] + marker
    return context


def extract_sql(text: str) -> str:
    """Pull the SQL out of an LLM reply (fenced block or raw).

    Args:
        text: The assistant text.

    Returns:
        The SQL with fences, surrounding whitespace, and trailing
        semicolons stripped.
    """
    match = _SQL_FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    return candidate.strip().rstrip(";").strip()


def _resolve_workspace_provider(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    settings: Settings,
) -> tuple[str, str, str]:
    """Pick the workspace's first enabled BYO LLM credential.

    Same credential rows the Lens chat-loop consumes; Genie has no
    per-space provider pin, so the first enabled provider (sorted by
    name) wins.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        settings: Resolved settings (model-default fallbacks).

    Returns:
        ``(provider_name, api_key, model)``.

    Raises:
        GenieLLMNotConfiguredError: When no enabled credential
            decrypts for the workspace.
    """
    from pointlessql.services.lens._provider_creds import (
        decrypt_provider_key,
        list_provider_creds,
    )

    for row in list_provider_creds(factory, workspace_id=workspace_id):
        if not row.enabled:
            continue
        api_key = decrypt_provider_key(factory, workspace_id=workspace_id, provider=row.provider)
        if api_key is None:
            continue
        default_model = (
            settings.lens.openai_model_default
            if row.provider == "openai"
            else settings.lens.anthropic_model_default
        )
        return row.provider, api_key, row.default_model or default_model
    raise GenieLLMNotConfiguredError(
        f"No enabled LLM credential for workspace {workspace_id}.  "
        "Add an OpenAI or Anthropic key via the Lens provider settings "
        "in the admin UI before asking Genie."
    )


async def generate_sql(
    question: str,
    context: str,
    history: list[GenieMessage],
    *,
    factory: sessionmaker[Session],
    workspace_id: int,
    settings: Settings,
) -> str:
    """Turn a natural-language question into one SELECT via the LLM.

    Reuses the Lens provider plumbing end to end — credential
    resolution, the adapter factory, and the transcript shaping
    (:class:`GenieMessage` rows duck-type the ``role`` / ``content``
    surface :func:`to_provider_history` reads).  The adapters expose
    only ``chat_with_tools``; the Lens tool schemas ride along
    unused because the system prompt pins the reply to SQL-only —
    re-implementing a tool-free provider call would fork the
    plumbing this surface is meant to share.

    Args:
        question: The user's typed question.
        context: Rendered output of :func:`build_context`.
        history: Recent prior turns (oldest first, NOT including
            *question* itself).
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace (credential scope).
        settings: Resolved settings (model defaults).

    A workspace without an enabled BYO credential propagates
    :class:`GenieLLMNotConfiguredError` from the provider
    resolution.

    Returns:
        The extracted SQL string.

    Raises:
        ValidationError: When the model returns no usable text.
    """
    from pointlessql.services.lens._chat_logic import to_provider_history
    from pointlessql.services.lens.llm_provider import get_provider

    provider_name, api_key, model = _resolve_workspace_provider(
        factory, workspace_id=workspace_id, settings=settings
    )
    provider = get_provider(provider_name, api_key=api_key)
    # GenieMessage rows expose the same ``role`` / ``content``
    # attributes the Lens transcript shaper reads; the cast bridges
    # the nominal type without copying rows.
    messages = to_provider_history(provider_name, cast("list[Any]", history))
    if provider_name == "anthropic":
        messages.append({"role": "user", "content": [{"type": "text", "text": question}]})
    else:
        messages.append({"role": "user", "content": question})
    completion = await provider.chat_with_tools(
        system=f"{GENIE_SYSTEM_PROMPT}\n\n{context}",
        messages=messages,
        model=model,
    )
    sql = extract_sql(completion.text or "")
    if not sql:
        raise ValidationError(
            "The model returned no SQL for this question.  Rephrase it "
            "or add a trusted example covering this shape."
        )
    return sql


def validate_generated_sql(sql: str, *, allowed_tables: list[str]) -> list[str]:
    """Parse + scope-check generated SQL against the curated list.

    Defence in depth on top of the per-user SELECT enforcement the
    execution path applies: even a privileged user's Genie answer
    must stay inside the room the curator drew.

    Args:
        sql: The extracted model output.
        allowed_tables: The space's curated three-part FQNs.

    Returns:
        The referenced table FQNs (all inside the curated list).

    Raises:
        ValidationError: When a referenced table is outside the
            space.  A non-SELECT or unparseable statement propagates
            :class:`pointlessql.pql.SQLParseError` (a
            ``ValidationError`` subclass) from :func:`prepare_sql`.
    """
    prepared = prepare_sql(sql)
    allowed = set(allowed_tables)
    strays = [ref for ref in prepared.refs if ref not in allowed]
    if strays:
        raise ValidationError(
            "The generated SQL references tables outside this space: "
            f"{', '.join(sorted(strays))}.  Ask the space owner to add "
            "them, or rephrase the question."
        )
    return prepared.refs
