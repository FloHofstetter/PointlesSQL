# pyright: reportPrivateUsage=false
"""Input / output port blocks for the visual data-product canvas.

Compile + schema-inference helpers split out of the former single-file
block registry.  Shared infrastructure and the public dispatch live in
:mod:`pointlessql.services.dp_canvas._blocks._base`; this module
registers its block types into the dispatch tables at import time.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.dp_canvas._blocks._base import (
    _COMPILE_DISPATCH,
    _FQN_RE,
    _INFER_DISPATCH,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
    _bad_config,
    _coerce_str,
    _coerce_str_list,
    _register,
    _unknown_schema,
)
from pointlessql.services.dp_canvas._types import CompileError, PinSchema

# --------------------------------------------------------------------- InputPort


def _compile_input_port(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    del inputs  # InputPort has no upstream pins to consume
    fqn = _coerce_str(cfg.get("table_fqn"))
    if not _FQN_RE.match(fqn):
        errors.append(_bad_config(node_id, "table_fqn must be a UC three-part name"))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {fqn}",
        output_schema=output_schema,
    )


def _infer_input_port(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del input_schemas
    fqn = _coerce_str(cfg.get("table_fqn"))
    if not _FQN_RE.match(fqn):
        errors.append(_bad_config(node_id, "table_fqn must be a UC three-part name"))
        return _unknown_schema()
    if seed is not None:
        return seed
    return _unknown_schema()


_register(BlockSpec(type_name="InputPort", input_pins=(), output_pins=(("out", "table"),)))


# --------------------------------------------------------------------- DataProduct (DP◫)


def _compile_data_product(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    """Compile a DP compound block — reads the *materialized table* of one chosen output port.

    The block stores the resolved 3-part UC name on save so the
    compiler stays pure; the route layer fills ``materialized_table``
    by looking up ``DataProductOutputPort`` for the chosen
    ``(dp_id, port_name)`` pair.
    """
    del inputs
    fqn = _coerce_str(cfg.get("materialized_table"))
    if not _FQN_RE.match(fqn):
        errors.append(
            _bad_config(
                node_id,
                "DataProduct.materialized_table must be a UC three-part name "
                "(resolved on save from the referenced output-port).",
            )
        )
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {fqn}",
        output_schema=output_schema,
    )


def _infer_data_product(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del input_schemas
    fqn = _coerce_str(cfg.get("materialized_table"))
    if not _FQN_RE.match(fqn):
        errors.append(
            _bad_config(
                node_id,
                "DataProduct.materialized_table must be a UC three-part name "
                "(resolved on save from the referenced output-port).",
            )
        )
        return _unknown_schema()
    if seed is not None:
        return seed
    return _unknown_schema()


_register(
    BlockSpec(
        type_name="DataProduct", input_pins=(), output_pins=(("out", "table"),)
    )
)



# --------------------------------------------------------------------- OutputPort


def _compile_output_port(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="OutputPort requires an upstream input on pin 'in'.",
            )
        )
        return None
    port_name = _coerce_str(cfg.get("port_name")).strip()
    if not port_name:
        errors.append(_bad_config(node_id, "OutputPort.port_name is required."))
        return None
    target = _coerce_str(cfg.get("materialized_table"))
    if not _FQN_RE.match(target):
        errors.append(
            _bad_config(node_id, "OutputPort.materialized_table must be a UC three-part name.")
        )
        return None
    mode = _coerce_str(cfg.get("mode"), default="overwrite").lower()
    if mode not in OUTPUT_MODES:
        errors.append(_bad_config(node_id, f"OutputPort.mode must be one of {OUTPUT_MODES}."))
        return None
    if mode == "merge":
        merge_on = _coerce_str_list(cfg.get("merge_on"))
        if not merge_on:
            errors.append(
                _bad_config(node_id, "OutputPort.merge_on is required when mode='merge'.")
            )
            return None
    return CompiledBlock(
        sql=f"SELECT * FROM {src}",
        output_schema=output_schema,
    )


def _infer_output_port(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del node_id, cfg, errors, seed
    return input_schemas.get("in", _unknown_schema())


_register(BlockSpec(type_name="OutputPort", input_pins=(("in", "table"),), output_pins=()))



_COMPILE_DISPATCH.update(
    {
        "InputPort": _compile_input_port,
        "DataProduct": _compile_data_product,
        "OutputPort": _compile_output_port,
    }
)
_INFER_DISPATCH.update(
    {
        "InputPort": _infer_input_port,
        "DataProduct": _infer_data_product,
        "OutputPort": _infer_output_port,
    }
)