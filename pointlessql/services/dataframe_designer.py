"""NL-prompt → DataFrame Studio pipeline generation.

The visual canvas + the sink-free DataFrame Studio compiler already turn
a typed block DAG into a governed DuckDB ``WITH … SELECT`` chain.  The
missing half is the AI generation: turning a natural-language request
into a pre-filled :class:`CanvasDoc` instead of just a SELECT.

This module is the deterministic backbone of that flow.  An LLM produces
a *plan* — an ordered list of transform steps — and
:func:`build_canvas_from_plan` maps it onto a linear chain of the allowed
single-input block types (rooted at an ``InputPort`` for the base table)
and runs it through :func:`validate_schema_flow`, so a malformed plan
surfaces as canvas validation errors rather than a broken graph.  The
provider round-trip is injected (:data:`Completer`) so the assembly +
validation is testable without a live model.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

# dp_canvas registers the InputPort source block into the shared registry.
import pointlessql.services.dp_canvas  # noqa: F401  # pyright: ignore[reportUnusedImport]
from pointlessql.services.ai_functions import Completer
from pointlessql.services.canvas_df import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    ColumnSpec,
    CompileError,
    PinSchema,
    validate_schema_flow,
)

logger = logging.getLogger(__name__)

#: The single-input transform blocks an NL-generated pipeline may use.
#: Restricted to single-pin blocks so the generated chain is always a
#: valid linear graph; multi-input blocks (Join / Union / …) and the I/O
#: ports are intentionally excluded.
ALLOWED_STEP_BLOCKS: tuple[str, ...] = (
    "Filter",
    "Project",
    "Rename",
    "Cast",
    "CalcColumn",
    "Sort",
    "Limit",
    "Distinct",
)


def build_canvas_from_plan(
    input_table: str,
    steps: list[dict[str, Any]],
    *,
    seed_schema: PinSchema | None = None,
) -> tuple[CanvasDoc | None, list[CompileError]]:
    """Assemble a linear canvas from a generated plan and validate it.

    The plan becomes ``InputPort(input_table) → step₁ → step₂ → …`` with
    each block's ``in`` pin wired to the previous block's ``out`` pin.

    Args:
        input_table: Three-part FQN of the base table the chain reads.
        steps: Ordered plan steps, each ``{"block_type", "config"}``.
        seed_schema: The base table's schema, seeded onto the
            ``InputPort`` so :func:`validate_schema_flow` can propagate
            real column types; ``None`` leaves it unknown.

    Returns:
        ``(doc, errors)``.  ``doc`` is ``None`` when the plan is
        structurally rejected (bad input table, unknown / disallowed
        block); otherwise it is the assembled document and ``errors``
        holds the schema-flow findings (empty when the plan is clean).
    """
    errors: list[CompileError] = []
    table = (input_table or "").strip()
    if not table:
        return None, [CompileError(kind="bad_config", message="input_table is required.")]

    nodes: list[CanvasNode] = [
        CanvasNode(id="n0", block_type="InputPort", config={"table_fqn": table})
    ]
    edges: list[CanvasEdge] = []
    prev_id = "n0"
    for index, step in enumerate(steps, start=1):
        block_type = str(step.get("block_type", "")).strip()
        if block_type not in ALLOWED_STEP_BLOCKS:
            errors.append(
                CompileError(
                    kind="unknown_block",
                    message=(
                        f"Block {block_type!r} is not allowed in a generated pipeline; "
                        f"use one of {list(ALLOWED_STEP_BLOCKS)}."
                    ),
                )
            )
            continue
        raw_cfg = step.get("config")
        config: dict[str, Any] = (
            cast("dict[str, Any]", raw_cfg) if isinstance(raw_cfg, dict) else {}
        )
        node_id = f"n{index}"
        nodes.append(CanvasNode(id=node_id, block_type=block_type, config=config))
        edges.append(
            CanvasEdge(
                id=f"e{index}",
                source_node_id=prev_id,
                source_pin="out",
                target_node_id=node_id,
                target_pin="in",
            )
        )
        prev_id = node_id

    if errors:
        return None, errors

    doc = CanvasDoc(nodes=nodes, edges=edges)
    seed = {"n0": seed_schema} if seed_schema is not None else None
    _, flow_errors = validate_schema_flow(doc, seed_schemas=seed)
    return doc, flow_errors


def seed_from_columns(columns: list[dict[str, Any]] | None) -> PinSchema | None:
    """Build an ``InputPort`` seed schema from a column descriptor list.

    Args:
        columns: Column dicts (``name`` + ``duckdb_type``/``type`` +
            optional ``nullable``), or ``None``.

    Returns:
        A :class:`PinSchema`, or ``None`` when no usable column is given.
    """
    specs: list[ColumnSpec] = []
    for column in columns or []:
        name = str(column.get("name") or "").strip()
        if not name:
            continue
        dtype = (
            str(column.get("duckdb_type") or column.get("type") or "VARCHAR").strip() or "VARCHAR"
        )
        specs.append(
            ColumnSpec(name=name, duckdb_type=dtype, nullable=bool(column.get("nullable", True)))
        )
    if not specs:
        return None
    return PinSchema(kind="table", columns=specs)


_SYSTEM_PROMPT = (
    "You are a data-pipeline designer for a visual ETL canvas. Given a base "
    "table, its columns, and a user request, reply with ONLY a JSON object of "
    'the form {"steps": [{"block_type": "...", "config": {...}}]}. Use only '
    "these block types, each a single-input transform applied in order: "
    "Filter (config.predicate: SQL boolean), Project (config.columns: list of "
    "kept column names), Rename (config.mapping: {old: new}), Cast "
    "(config.casts: {column: duckdb_type}), CalcColumn (config.name + "
    "config.expr), Sort (config.by: list, config.descending: bool), Limit "
    "(config.n: int), Distinct (no config). Return no prose."
)


def _build_user_prompt(prompt: str, input_table: str, columns: list[dict[str, Any]] | None) -> str:
    """Render the user message describing the table + request."""
    col_text = ", ".join(
        f"{c.get('name')}:{c.get('duckdb_type') or c.get('type') or 'VARCHAR'}"
        for c in (columns or [])
        if c.get("name")
    )
    return f"Base table: {input_table}\nColumns: {col_text or '(unknown)'}\nRequest: {prompt}"


def _parse_plan(raw: str) -> tuple[list[dict[str, Any]], str | None]:
    """Extract the ``steps`` list from a model's raw JSON reply.

    Args:
        raw: The model's completion text.

    Returns:
        ``(steps, error)`` — ``error`` is non-``None`` when the reply
        carried no parseable ``steps`` array.
    """
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return [], "Model reply contained no JSON object."
    try:
        loaded: Any = json.loads(match.group(0))
    except ValueError:
        return [], "Model reply was not valid JSON."
    if not isinstance(loaded, dict):
        return [], "Model reply was not a JSON object."
    raw_steps = cast("dict[str, Any]", loaded).get("steps")
    if not isinstance(raw_steps, list):
        return [], "Model reply had no 'steps' array."
    steps = cast("list[Any]", raw_steps)
    return [cast("dict[str, Any]", s) for s in steps if isinstance(s, dict)], None


def generate_pipeline(
    *,
    prompt: str,
    input_table: str,
    columns: list[dict[str, Any]] | None,
    complete: Completer,
) -> dict[str, Any]:
    """Generate a validated canvas document from a natural-language prompt.

    Args:
        prompt: The analyst's natural-language pipeline request.
        input_table: Three-part FQN of the base table to read.
        columns: The base table's columns (for the seed schema +
            the model prompt).
        complete: Injected provider round-trip ``(system, user) -> str``.

    Returns:
        ``{"document", "errors", "steps"}`` — ``document`` is the
        serialised :class:`CanvasDoc` (or ``None`` on a structural
        rejection / parse failure), ``errors`` the validation findings,
        and ``steps`` the parsed plan.
    """
    user_prompt = _build_user_prompt(prompt, input_table, columns)
    try:
        raw = complete(_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # noqa: BLE001 — any provider/transport failure becomes a surfaced finding, not a 500
        logger.exception("pipeline generation: provider completion failed")
        return {
            "document": None,
            "errors": [{"kind": "provider_error", "message": f"AI provider call failed: {exc}"}],
            "steps": [],
        }
    steps, parse_error = _parse_plan(raw)
    if parse_error is not None:
        return {
            "document": None,
            "errors": [{"kind": "bad_config", "message": parse_error}],
            "steps": [],
        }
    doc, errors = build_canvas_from_plan(input_table, steps, seed_schema=seed_from_columns(columns))
    return {
        "document": doc.model_dump() if doc is not None else None,
        "errors": [error.model_dump() for error in errors],
        "steps": steps,
    }
