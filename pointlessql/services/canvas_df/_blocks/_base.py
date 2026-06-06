# pyright: reportUnusedFunction=false
"""Block-type registry for the visual data-product canvas.

Each block is a tiny adapter that knows two things:

* :py:meth:`BlockSpec.compile` — turn an ``(inputs, config)`` pair
  into a DuckDB CTE body the compiler can splice into the final
  ``WITH … SELECT …`` rendering.
* :py:meth:`BlockSpec.infer_output` — given the same inputs, declare
  the downstream :class:`PinSchema` so the schema-flow validator can
  propagate types forward and surface edit-time mismatches without
  ever touching DuckDB.

Both methods are *pure* — they never read settings, never hit soyuz,
never open a database connection.  Side-effects live in the executor.

This module holds only the shared infrastructure: the ``BlockSpec`` /
``CompiledBlock`` dataclasses, the ``BLOCK_REGISTRY``, and the public
:func:`compile_block` / :func:`infer_block` entry points.  Each block
lives in its own ``_compile_*`` / ``_infer_*`` helper in a per-category
sibling module (``_io`` / ``_relational`` / ``_reshape`` / ``_columns``
/ ``_sql``) that calls :func:`register_block` at import time, so a new
block drops into a category module without editing this core.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pointlessql.services.canvas_df._types import (
    ColumnSpec,
    CompileError,
    PinSchema,
)

_FQN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class CompiledBlock:
    """One block's compiled contribution to the SQL fragment."""

    sql: str
    output_schema: PinSchema


# Compile + schema-inference function signatures.  Both are pure: given
# a node's resolved inputs + config they return the CTE body / output
# schema, appending to the shared error list on bad config.
_CompileFn = Callable[
    [str, dict[str, str], PinSchema, dict[str, Any], list[CompileError]],
    "CompiledBlock | None",
]
_InferFn = Callable[..., PinSchema]


@dataclass(frozen=True)
class BlockSpec:
    """One block type: its pin shape plus its pure compile + infer fns.

    Attributes:
        type_name: Registry key.
        input_pins: Ordered list of ``(pin_name, pin_kind)``.  v1
            only carries ``"table"`` pins, but the tuple shape leaves
            room for ``"scalar"`` / ``"model"`` later without
            re-spelling the registry.
        output_pins: Same shape; ``OutputPort`` has none.
        compile_fn: Turns ``(inputs, config)`` into a CTE body.
        infer_fn: Declares the output :class:`PinSchema` for schema-flow.
    """

    type_name: str
    input_pins: tuple[tuple[str, Literal["table"]], ...]
    output_pins: tuple[tuple[str, Literal["table"]], ...]
    compile_fn: _CompileFn
    infer_fn: _InferFn


BLOCK_REGISTRY: dict[str, BlockSpec] = {}


def register_block(
    type_name: str,
    *,
    input_pins: tuple[tuple[str, Literal["table"]], ...],
    output_pins: tuple[tuple[str, Literal["table"]], ...],
    compile_fn: _CompileFn,
    infer_fn: _InferFn,
) -> None:
    """Register one block type into :data:`BLOCK_REGISTRY`.

    Called once per block at import time from a category module, right
    after that block's ``_compile_*`` / ``_infer_*`` helpers are defined.
    The package ``__init__`` imports every category module so these
    registrations run before anything reads the registry.
    """
    BLOCK_REGISTRY[type_name] = BlockSpec(
        type_name=type_name,
        input_pins=input_pins,
        output_pins=output_pins,
        compile_fn=compile_fn,
        infer_fn=infer_fn,
    )


# --------------------------------------------------------------------- helpers


def _coerce_str(value: Any, *, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str | int | float) and str(v)]
    return []


def _bad_config(
    node_id: str,
    message: str,
    *,
    column: str | None = None,
    suggestion: str | None = None,
) -> CompileError:
    """Build a ``bad_config`` error, optionally tagged for the editor drawer.

    ``column`` and ``suggestion`` let the per-block settings panel associate
    the error with the specific input field it implicates (and highlight it),
    rather than only listing the message — they are the structured hooks the
    drawer reads, so a bare message still works for callers that omit them.
    """
    return CompileError(
        kind="bad_config",
        node_id=node_id,
        pin=None,
        message=message,
        column=column,
        suggestion=suggestion,
    )


def _schema_columns(schema: PinSchema) -> dict[str, ColumnSpec]:
    return {col.name: col for col in schema.columns}


def _unknown_schema() -> PinSchema:
    return PinSchema(kind="table", columns=[], unknown=True)



# --------------------------------------------------------------------- output modes

OUTPUT_MODES: tuple[str, ...] = ("overwrite", "append", "merge")


# --------------------------------------------------------------------- dispatch


def compile_block(
    *,
    block_type: str,
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    """Dispatch to the per-type compile helper.

    Returns ``None`` and appends to *errors* on failure so the compiler
    keeps marching through the rest of the graph rather than aborting
    at the first issue.
    """
    spec = BLOCK_REGISTRY.get(block_type)
    if spec is None:
        errors.append(
            CompileError(
                kind="unknown_block",
                node_id=node_id,
                pin=None,
                message=f"Unknown block_type {block_type!r}.",
            )
        )
        return None
    return spec.compile_fn(node_id, inputs, output_schema, cfg, errors)


def infer_block(
    *,
    block_type: str,
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    seed: PinSchema | None = None,
) -> PinSchema:
    """Dispatch to the per-type schema-inference helper."""
    spec = BLOCK_REGISTRY.get(block_type)
    if spec is None:
        errors.append(
            CompileError(
                kind="unknown_block",
                node_id=node_id,
                pin=None,
                message=f"Unknown block_type {block_type!r}.",
            )
        )
        return _unknown_schema()
    return spec.infer_fn(node_id, input_schemas, cfg, errors, seed=seed)