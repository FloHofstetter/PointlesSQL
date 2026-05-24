"""Canvas → PQL compiler.

Translates a linear pipeline of typed nodes into a short PQL
script that the supervision-mode UI shows alongside the canvas.

Linear-only by design: each node consumes exactly one DataFrame
(except the head, ``read_dp``) and emits one (except the tail,
``write_dp``).  Branches / fan-out / fan-in are explicitly out of
scope .
"""

from __future__ import annotations

import re
from typing import Any, cast

SUPPORTED_NODE_KINDS: tuple[str, ...] = (
    "read_dp",
    "filter",
    "join",
    "group_by",
    "run_model",
    "write_dp",
)

_FQN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def compile_nodes(nodes: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Render *nodes* to a PQL script + collected errors.

    The first node must be ``read_dp`` and the last must be
    ``write_dp`` (or ``run_model`` when running an inference job
    against the pipeline output).  Intermediate nodes are emitted
    in order.

    Args:
        nodes: Ordered list of ``{kind, config}`` dicts.

    Returns:
        ``(code, errors)``.  ``code`` is empty when *errors* is
        non-empty.
    """
    errors: list[str] = []
    if not nodes:
        return "", ["Canvas is empty — add at least a read_dp and a write_dp node."]

    kinds = [n.get("kind") for n in nodes]
    if kinds[0] != "read_dp":
        errors.append("The first node must be a read_dp (source).")
    if kinds[-1] not in ("write_dp", "run_model"):
        errors.append("The last node must be a write_dp or run_model (sink).")
    for idx, k in enumerate(kinds):
        if k not in SUPPORTED_NODE_KINDS:
            errors.append(f"Node {idx}: unsupported kind {k!r}.")
        if idx > 0 and k == "read_dp":
            errors.append(f"Node {idx}: read_dp may only appear as the first node.")
        if idx < len(kinds) - 1 and k in ("write_dp", "run_model"):
            errors.append(f"Node {idx}: {k} must be the last node — branching is not supported.")

    if errors:
        return "", errors

    lines: list[str] = [
        "from pointlessql import PQL",
        "",
        "pql = PQL()",
    ]
    var_counter = 0
    current_var = "df"
    for idx, node in enumerate(nodes):
        kind = str(node["kind"])
        cfg = cast(dict[str, Any], node.get("config") or {})
        if kind == "read_dp":
            fqn = str(cfg.get("table_fqn") or "")
            if not _FQN_RE.match(fqn):
                errors.append(f"read_dp node {idx}: table_fqn must be three-part.")
                continue
            lines.append(f'{current_var} = pql.read_table("{fqn}")')
        elif kind == "filter":
            predicate = str(cfg.get("predicate") or "").strip()
            if not predicate:
                errors.append(f"filter node {idx}: predicate is required.")
                continue
            lines.append(f"{current_var} = {current_var}.query({predicate!r})")
        elif kind == "join":
            right_fqn = str(cfg.get("right_table_fqn") or "")
            on_col = str(cfg.get("on") or "")
            how = str(cfg.get("how") or "inner")
            if not _FQN_RE.match(right_fqn):
                errors.append(f"join node {idx}: right_table_fqn must be three-part.")
                continue
            if not on_col:
                errors.append(f"join node {idx}: 'on' column is required.")
                continue
            var_counter += 1
            tmp = f"right_{var_counter}"
            lines.append(f'{tmp} = pql.read_table("{right_fqn}")')
            lines.append(f"{current_var} = {current_var}.merge({tmp}, on={on_col!r}, how={how!r})")
        elif kind == "group_by":
            cols = cfg.get("columns") or []
            aggs = cfg.get("aggregates") or {}
            if not isinstance(cols, list) or not cols:
                errors.append(f"group_by node {idx}: at least one column is required.")
                continue
            if not isinstance(aggs, dict) or not aggs:
                errors.append(f"group_by node {idx}: at least one aggregate is required.")
                continue
            lines.append(
                f"{current_var} = {current_var}.groupby({list(cols)!r})"
                f".agg({dict(aggs)!r}).reset_index()"
            )
        elif kind == "run_model":
            model_uri = str(cfg.get("model_uri") or "")
            if not model_uri:
                errors.append(f"run_model node {idx}: model_uri is required.")
                continue
            lines.append(f'predictions = pql.run_model("{model_uri}", {current_var})')
            current_var = "predictions"
        elif kind == "write_dp":
            target = str(cfg.get("target_fqn") or "")
            mode = str(cfg.get("mode") or "overwrite")
            if not _FQN_RE.match(target):
                errors.append(f"write_dp node {idx}: target_fqn must be three-part.")
                continue
            if mode not in ("append", "overwrite", "merge"):
                errors.append(f"write_dp node {idx}: mode must be append / overwrite / merge.")
                continue
            if mode == "merge":
                on_col = str(cfg.get("on") or "")
                if not on_col:
                    errors.append(f"write_dp node {idx}: merge mode requires 'on'.")
                    continue
                lines.append(f'pql.merge("{target}", {current_var}, on={on_col!r})')
            else:
                lines.append(f'pql.write_table("{target}", {current_var}, mode={mode!r})')

    if errors:
        return "", errors
    return "\n".join(lines) + "\n", []
