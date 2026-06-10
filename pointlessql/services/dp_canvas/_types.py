"""Pydantic types for the visual data-product canvas.

The graph envelope (:class:`CanvasDoc` / :class:`CanvasNode` /
:class:`CanvasEdge`) and the shared :class:`CompileError` live in the
consumer-agnostic :mod:`pointlessql.services.canvas_core` kernel; the
dataframe-flavoured pin/compiler shapes (:class:`ColumnSpec` /
:class:`PinSchema` / :class:`SinkSpec` / :class:`SQLFragment`) live in the
reusable :mod:`pointlessql.services.canvas_df` layer.  Both groups are
re-exported here so every existing ``from pointlessql.services.dp_canvas
import …`` (and ``from …dp_canvas._types import …``) keeps resolving
unchanged.

What stays here is the *data-product-specific* tail of the contract — the
executor's per-sink results.  These name Unity Catalog output ports and the
``data_product_canvas_graph`` version a materialise run stamps, so they only
make sense for the data-product pipeline that owns those tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.services.canvas_core._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
)
from pointlessql.services.canvas_df._types import (
    ColumnSpec,
    PinSchema,
    SinkSpec,
    SQLFragment,
)


class SinkResult(BaseModel):
    """The per-sink outcome of one :func:`execute_canvas` run.

    Attributes:
        model_config: Pydantic configuration; ``frozen=True`` keeps
            the result immutable once the executor emits it.
        port_name: ``OutputPort.config.port_name`` this result belongs to.
        target_fqn: Three-part UC name this sink materialised to.
        rows_written: Rows written into the target Delta table; ``0`` when
            the sink failed before any write.
        output_port_id: PK of the ``data_product_output_ports`` row
            registered for the materialised table.  ``None`` when an
            existing port with the same name was reused or the sink failed.
        status: ``"ok"`` when the write + registration succeeded,
            ``"failed"`` when this sink raised mid-run (other sinks still
            run — materialisation is best-effort per sink).
        error: Human-readable failure summary when ``status == "failed"``.
    """

    model_config = ConfigDict(frozen=True)

    port_name: str
    target_fqn: str
    rows_written: int = 0
    output_port_id: int | None = None
    status: Literal["ok", "failed"]
    error: str | None = None


class MultiExecuteResult(BaseModel):
    """The return envelope of :func:`execute_canvas`.

    A canvas may publish several output ports; ``sinks`` carries one
    :class:`SinkResult` per ``OutputPort`` block, in document order.
    Config / compile errors short-circuit before any write (the call
    raises); a *runtime* write failure on one sink leaves the others
    untouched and surfaces as that sink's ``status == "failed"``.

    Attributes:
        model_config: Pydantic configuration; ``frozen=True`` keeps
            the envelope immutable once the executor returns it.
        sinks: Per-sink outcomes for this run (at least one).
        graph_version: ``version`` the executor stamped on the single
            ``data_product_canvas_graph`` row minted for this run — all
            sinks share it.
        compile_errors: Always empty on a successful run; reserved for
            callers that want to inspect dry-run output in future waves.
    """

    model_config = ConfigDict(frozen=True)

    sinks: list[SinkResult] = Field(default_factory=list)
    graph_version: int
    compile_errors: Sequence[CompileError] = Field(default_factory=list)


__all__ = [
    "CanvasDoc",
    "CanvasEdge",
    "CanvasNode",
    "ColumnSpec",
    "CompileError",
    "MultiExecuteResult",
    "PinSchema",
    "SQLFragment",
    "SinkResult",
    "SinkSpec",
]
