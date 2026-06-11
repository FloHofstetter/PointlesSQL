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

import datetime
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select

from pointlessql.models.genie import (
    GENIE_FEEDBACK_VALUES,
    GenieMessage,
    GenieSpace,
    GenieTrustedAsset,
)
from pointlessql.pql import prepare_sql

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


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


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _slugify(title: str) -> str:
    """Derive a collision-proof slug from *title* (mirrors BI dashboards)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "space"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _validate_fqn_list(value: Any, *, what: str) -> list[str]:
    """Normalise a curated-FQN list, rejecting malformed entries.

    Args:
        value: Candidate list of dotted full names.
        what: Noun for the error message (``"tables"`` /
            ``"metric_views"``).

    Returns:
        The de-duplicated list in first-appearance order.

    Raises:
        ValueError: On non-list input or an entry that is not a
            three-part dotted name.
    """
    if not isinstance(value, list):
        raise ValueError(f"{what} must be a list of catalog.schema.name strings")
    seen: set[str] = set()
    out: list[str] = []
    for raw in cast("list[object]", value):
        name = str(raw).strip()
        if not _FQN_RE.match(name):
            raise ValueError(f"{what} entry {name!r} must be a three-part catalog.schema.name")
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def create_space(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    title: str,
    description: str | None,
    owner_id: int,
) -> GenieSpace:
    """Create an empty Genie space.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        title: Human-readable name (slug derives from it).
        description: Optional free-form description.
        owner_id: Creating user's id.

    Returns:
        The persisted space row (detached).

    Raises:
        ValueError: On an empty title.
    """
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("title must be a non-empty string")
    now = _utcnow()
    row = GenieSpace(
        workspace_id=workspace_id,
        slug=_slugify(cleaned),
        title=cleaned,
        description=description,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_spaces(factory: sessionmaker[Session], *, workspace_id: int) -> list[GenieSpace]:
    """List the workspace's spaces, newest-updated first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached space rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(GenieSpace)
                .where(GenieSpace.workspace_id == workspace_id)
                .order_by(GenieSpace.updated_at.desc())
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_space(factory: sessionmaker[Session], *, workspace_id: int, slug: str) -> GenieSpace | None:
    """Return the workspace's space by slug, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        slug: Space slug.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(GenieSpace).where(
                GenieSpace.workspace_id == workspace_id,
                GenieSpace.slug == slug,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def update_space(
    factory: sessionmaker[Session],
    *,
    space_id: int,
    title: Any = _UNSET,
    description: Any = _UNSET,
    instructions: Any = _UNSET,
    tables: Any = _UNSET,
    metric_views: Any = _UNSET,
) -> GenieSpace | None:
    """Patch a space's curation fields.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Primary key.
        title: New title, or unset to keep.
        description: New description (``None`` clears), or unset.
        instructions: New curator instructions (``None`` clears), or
            unset.
        tables: New curated three-part-FQN list, or unset.
        metric_views: New metric-view full-name list, or unset.

    Returns:
        The refreshed detached row, or ``None`` when absent.

    Raises:
        ValueError: On an empty title or a malformed FQN list.
    """
    with factory() as session:
        row = session.get(GenieSpace, space_id)
        if row is None:
            return None
        if title is not _UNSET:
            cleaned = str(title).strip()
            if not cleaned:
                raise ValueError("title must be a non-empty string")
            row.title = cleaned
        if description is not _UNSET:
            row.description = description
        if instructions is not _UNSET:
            row.instructions = instructions
        if tables is not _UNSET:
            row.tables = json.dumps(_validate_fqn_list(tables, what="tables"))
        if metric_views is not _UNSET:
            row.metric_views = json.dumps(_validate_fqn_list(metric_views, what="metric_views"))
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_space(factory: sessionmaker[Session], *, space_id: int) -> bool:
    """Delete a space, its trusted assets, and its transcript.

    Children go explicitly in the same transaction (same rationale
    as the BI-dashboard delete: SQLite only cascades with the FK
    pragma on).

    Args:
        factory: SQLAlchemy session factory.
        space_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(GenieSpace, space_id)
        if row is None:
            return False
        session.execute(delete(GenieTrustedAsset).where(GenieTrustedAsset.space_id == space_id))
        session.execute(delete(GenieMessage).where(GenieMessage.space_id == space_id))
        session.delete(row)
        session.commit()
    return True


def space_tables(space: GenieSpace) -> list[str]:
    """Return the space's curated table FQNs (decoded JSON column)."""
    return [str(t) for t in json.loads(space.tables or "[]")]


def space_metric_views(space: GenieSpace) -> list[str]:
    """Return the space's curated metric-view full names."""
    return [str(m) for m in json.loads(space.metric_views or "[]")]


def add_trusted_asset(
    factory: sessionmaker[Session],
    *,
    space_id: int,
    question: str,
    sql_text: str,
    created_by: int,
) -> GenieTrustedAsset:
    """Add one curator-approved Q→SQL example to a space.

    The SQL is parsed up front so a curator typo cannot poison the
    few-shot examples with something the execution path would reject
    anyway.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Owning space's primary key.
        question: The natural-language phrasing.
        sql_text: The vetted SQL (must parse as a single SELECT).
        created_by: Curating user's id.

    Returns:
        The persisted asset row (detached).

    Raises:
        ValueError: On an empty question / SQL.  A non-SELECT or
            unparseable ``sql_text`` propagates
            :class:`pointlessql.pql.SQLParseError` (itself a
            ``ValueError`` subclass) from :func:`prepare_sql`.
    """
    cleaned_question = question.strip()
    cleaned_sql = sql_text.strip()
    if not cleaned_question:
        raise ValueError("question must be a non-empty string")
    if not cleaned_sql:
        raise ValueError("sql_text must be a non-empty string")
    prepare_sql(cleaned_sql)
    now = _utcnow()
    row = GenieTrustedAsset(
        space_id=space_id,
        question=cleaned_question[:500],
        sql_text=cleaned_sql,
        created_by=created_by,
        created_at=now,
    )
    with factory() as session:
        session.add(row)
        space = session.get(GenieSpace, space_id)
        if space is not None:
            space.updated_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_trusted_assets(
    factory: sessionmaker[Session], *, space_id: int
) -> list[GenieTrustedAsset]:
    """List a space's trusted assets, oldest first.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Owning space's primary key.

    Returns:
        Detached asset rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(GenieTrustedAsset)
                .where(GenieTrustedAsset.space_id == space_id)
                .order_by(GenieTrustedAsset.id)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def delete_trusted_asset(factory: sessionmaker[Session], *, space_id: int, asset_id: int) -> bool:
    """Delete one trusted asset of one space.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Owning space's primary key (guards against
            cross-space asset ids in the URL).
        asset_id: Asset primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(GenieTrustedAsset, asset_id)
        if row is None or row.space_id != space_id:
            return False
        session.delete(row)
        session.commit()
    return True


def append_message(
    factory: sessionmaker[Session],
    *,
    space_id: int,
    user_id: int | None,
    role: str,
    content: str,
    sql_text: str | None = None,
    status: str = "ok",
    error: str | None = None,
) -> GenieMessage:
    """Append one turn to a space's shared transcript.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Owning space's primary key.
        user_id: Asking user's id (``None`` on assistant rows).
        role: ``user`` or ``assistant``.
        content: Natural-language text of the turn.
        sql_text: Generated SQL on assistant rows.
        status: ``ok`` or ``error``.
        error: Failure detail on ``error`` rows.

    Returns:
        The persisted message row (detached).
    """
    row = GenieMessage(
        space_id=space_id,
        user_id=user_id,
        role=role,
        content=content,
        sql_text=sql_text,
        status=status,
        error=error,
        created_at=_utcnow(),
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_messages(
    factory: sessionmaker[Session], *, space_id: int, limit: int = 50
) -> list[GenieMessage]:
    """Return the last *limit* turns of a space, oldest first.

    Args:
        factory: SQLAlchemy session factory.
        space_id: Owning space's primary key.
        limit: Tail size (the room only replays recent history).

    Returns:
        Detached message rows in chronological order.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(GenieMessage)
                .where(GenieMessage.space_id == space_id)
                .order_by(GenieMessage.id.desc())
                .limit(limit)
            )
        )
        for row in rows:
            session.expunge(row)
    return list(reversed(rows))


def get_message(factory: sessionmaker[Session], *, message_id: int) -> GenieMessage | None:
    """Return one message by primary key, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        message_id: Message primary key.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.get(GenieMessage, message_id)
        if row is not None:
            session.expunge(row)
    return row


def set_feedback(
    factory: sessionmaker[Session], *, message_id: int, feedback: str
) -> GenieMessage | None:
    """Record a thumbs reaction on an assistant message.

    Args:
        factory: SQLAlchemy session factory.
        message_id: Message primary key.
        feedback: One of :data:`GENIE_FEEDBACK_VALUES`.

    Returns:
        The refreshed detached row, or ``None`` when absent.

    Raises:
        ValueError: On an unknown feedback value or a non-assistant
            target message.
    """
    if feedback not in GENIE_FEEDBACK_VALUES:
        raise ValueError(f"feedback must be one of {', '.join(GENIE_FEEDBACK_VALUES)}")
    with factory() as session:
        row = session.get(GenieMessage, message_id)
        if row is None:
            return None
        if row.role != "assistant":
            raise ValueError("feedback applies to assistant messages only")
        row.feedback = feedback
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def promote_message(
    factory: sessionmaker[Session], *, message_id: int, created_by: int
) -> GenieTrustedAsset:
    """Promote an assistant answer into the trusted-asset list.

    The question is the closest preceding ``user`` turn in the same
    space — the flat shared-room transcript makes that the turn the
    answer responded to.

    Args:
        factory: SQLAlchemy session factory.
        message_id: Assistant message primary key.
        created_by: Promoting curator's user id.

    Returns:
        The created asset row (detached).

    Raises:
        ValueError: When the message is missing, is not a successful
            assistant turn with SQL, or no preceding question exists.
    """
    with factory() as session:
        row = session.get(GenieMessage, message_id)
        if row is None:
            raise ValueError(f"message {message_id} not found")
        if row.role != "assistant" or row.status != "ok" or not row.sql_text:
            raise ValueError("only successful assistant answers with SQL can be promoted")
        question_row = session.scalar(
            select(GenieMessage)
            .where(
                GenieMessage.space_id == row.space_id,
                GenieMessage.role == "user",
                GenieMessage.id < row.id,
            )
            .order_by(GenieMessage.id.desc())
        )
        if question_row is None:
            raise ValueError("no preceding question found to promote with the answer")
        space_id = row.space_id
        question = question_row.content
        sql_text = row.sql_text
    return add_trusted_asset(
        factory,
        space_id=space_id,
        question=question,
        sql_text=sql_text,
        created_by=created_by,
    )
