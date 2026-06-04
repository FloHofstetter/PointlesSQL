"""Pure YAML-diff engine for data-product schema-change proposals.

Request-free helpers that validate a proposed schema diff, decide whether
it is safe to apply in place, and rewrite the product's YAML accordingly.
Extracted from the proposals route module so the diff logic is testable
without an HTTP layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pointlessql.exceptions import (
    BadRequestError,
)

SAFE_INPLACE_DIFF_OPS: tuple[str, ...] = ("add_columns", "change_descriptions")


def validate_diff(diff: Any) -> dict[str, Any]:
    """Coerce + validate the body diff into a serialisable dict.

    Args:
        diff: The raw ``diff`` body value.

    Returns:
        Validated diff dict.

    Raises:
        HTTPException: 400 on unsupported diff op keys.
    """
    if not isinstance(diff, dict):
        raise BadRequestError("diff must be an object")
    allowed_keys: set[str] = {
        "add_columns",
        "remove_columns",
        "change_columns",
        "change_descriptions",
    }
    out: dict[str, Any] = {}
    raw_items: list[tuple[Any, Any]] = list(diff.items())  # pyright: ignore[reportUnknownVariableType]
    for key, val in raw_items:
        key_str = str(key)
        if key_str not in allowed_keys:
            raise BadRequestError(f"unknown diff key '{key_str}'")
        out[key_str] = val
    return out


def is_safe_for_inplace(diff: dict[str, Any]) -> bool:
    """Return True when the diff only contains additive / description ops.

    Args:
        diff: The validated diff dict.

    Returns:
        True if every key is in :data:`SAFE_INPLACE_DIFF_OPS`.
    """
    if not diff:
        return True
    return all(k in SAFE_INPLACE_DIFF_OPS for k in diff)


def apply_diff_to_yaml(
    yaml_text: str,
    diff: dict[str, Any],
) -> str:
    """Apply a safe diff to an existing yaml string.

    Supports the two safe operations:

    * ``add_columns`` — ``{table_name: [{name, type, nullable?,
      description?}, ...]}``
    * ``change_descriptions`` — ``{table_name: {column_name:
      new_description, ...}}``

    Args:
        yaml_text: Source yaml content (must be loader-shaped
            with a top-level ``data_product`` key).
        diff: The validated diff dict.

    Returns:
        Updated yaml string.
    """
    raw_any: Any = yaml.safe_load(yaml_text) or {}
    raw: dict[str, Any] = raw_any if isinstance(raw_any, dict) else {}
    block_any: Any = raw.get("data_product") or {}
    block: dict[str, Any] = dict(block_any) if isinstance(block_any, dict) else {}
    tables_any: Any = block.get("tables") or []
    tables: list[Any] = list(tables_any) if isinstance(tables_any, list) else []
    by_name: dict[str, dict[str, Any]] = {}
    for raw_t in tables:
        if not isinstance(raw_t, dict):
            continue
        t: dict[str, Any] = dict(raw_t)
        name = t.get("name")
        if isinstance(name, str):
            by_name[name] = t

    add_columns: dict[str, Any] = diff.get("add_columns") or {}
    for table_name, new_cols_any in add_columns.items():
        target = by_name.get(str(table_name))
        if target is None:
            continue
        cols_any: Any = target.get("columns") or []
        cols: list[dict[str, Any]] = (
            [dict(c) for c in cols_any if isinstance(c, dict)] if isinstance(cols_any, list) else []
        )
        existing = {c.get("name") for c in cols}
        new_cols_list: list[Any] = list(new_cols_any) if isinstance(new_cols_any, list) else []
        for new_col in new_cols_list:
            if not isinstance(new_col, dict) or new_col.get("name") in existing:
                continue
            cols.append(dict(new_col))
        target["columns"] = cols
        by_name[str(table_name)] = target

    change_descriptions: dict[str, Any] = diff.get("change_descriptions") or {}
    for table_name, updates_any in change_descriptions.items():
        target = by_name.get(str(table_name))
        if target is None or not isinstance(updates_any, dict):
            continue
        cols_any2: Any = target.get("columns") or []
        cols2: list[dict[str, Any]] = (
            [dict(c) for c in cols_any2 if isinstance(c, dict)]
            if isinstance(cols_any2, list)
            else []
        )
        for col in cols2:
            new_desc = updates_any.get(col.get("name"))
            if new_desc is not None:
                col["description"] = str(new_desc)
        target["columns"] = cols2
        by_name[str(table_name)] = target

    block["tables"] = [
        by_name[str(t.get("name"))]
        for t in tables
        if isinstance(t, dict) and isinstance(t.get("name"), str) and str(t.get("name")) in by_name
    ]
    return yaml.safe_dump({"data_product": block}, sort_keys=False)


def find_yaml_for_dp(
    settings: Any,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> Path | None:
    """Walk ``yaml_search_paths`` for the active DP's yaml file.

    Args:
        settings: Live :class:`Settings`.
        workspace_id: Tenant scope (unused — the loader already
            scopes by it via the path search).
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        The first matching yaml path or ``None``.
    """
    del workspace_id
    target_name = f"{catalog}__{schema}.yaml"
    for root in settings.data_products.yaml_search_paths:
        root_path = Path(root)
        if not root_path.exists():
            continue
        candidate = root_path / target_name
        if candidate.exists():
            return candidate
        # Generic "pointlessql.yaml" in the same directory tree.
        for path in root_path.rglob("*.yaml"):
            try:
                raw_any: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            if not isinstance(raw_any, dict):
                continue
            block_any: Any = raw_any.get("data_product") or {}
            if (
                isinstance(block_any, dict)
                and block_any.get("catalog") == catalog
                and block_any.get("schema") == schema
            ):
                return path
    return None
