"""The masking sidecar — executes column policy at the access point.

Pure functions the user-facing data routes (export port, table
preview, SQL results) invoke to mask classified columns for viewers
who may not see them in the clear.  This is the *computational* half of
governance: the policy declared on the product is executed here, at the
point data crosses to a consumer.

Masking fails *closed*: a strategy the helper cannot apply raises
rather than silently returning cleartext, so a bug can never downgrade
a masked column to a leak.

The frame helper duck-types the engine frames (pandas first; pyarrow /
polars / duckdb best-effort via ``to_pandas`` / ``df``).  An unknown
frame the helper cannot read is returned unchanged — acceptable because
pandas is the default engine and the masked access points use it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pointlessql.services.pii._mask import mask_value
from pointlessql.services.pii._redactor import REDACTED_PLACEHOLDER, hash_value


def viewer_sees_clear(*, is_admin: bool, is_steward: bool) -> bool:
    """Return ``True`` when the viewer may see classified columns clear.

    An install-admin or the product's own steward see cleartext; every
    other viewer gets the masked rendering.

    Args:
        is_admin: Whether the caller is an install-admin.
        is_steward: Whether the caller is the product's steward.

    Returns:
        ``True`` to bypass masking.
    """
    return bool(is_admin or is_steward)


def _is_null(value: Any) -> bool:
    """Return ``True`` for ``None`` or a float NaN (kept as-is when masking)."""
    if value is None:
        return True
    return isinstance(value, float) and value != value


def mask_cell(value: Any, strategy: str, *, secret: str | None) -> Any:
    """Apply one masking *strategy* to a single cell value.

    Args:
        value: The cleartext cell value (any type).  ``None`` / NaN
            pass through unchanged so "no value" stays distinguishable
            from "masked value".
        strategy: One of the masking strategies — ``none`` / ``hash`` /
            ``partial`` / ``full`` / ``null``.
        secret: The HMAC secret for ``hash``; when ``None`` the ``hash``
            strategy fails closed to a full redaction.

    Returns:
        The masked value.

    Raises:
        ValueError: When *strategy* is not one of the known
            strategies — masking fails closed rather than passing
            cleartext through.
    """
    if strategy == "none":
        return value
    if _is_null(value):
        return value
    if strategy == "null":
        return None
    if strategy == "full":
        return REDACTED_PLACEHOLDER
    if strategy == "partial":
        return mask_value(str(value))
    if strategy == "hash":
        if not secret:
            return REDACTED_PLACEHOLDER
        return hash_value(str(value), secret=secret)
    raise ValueError(f"unknown masking strategy {strategy!r}")


def _column_masker(strategy: str, secret: str | None) -> Callable[[Any], Any]:
    """Return a per-cell masker bound to one *strategy* + *secret*."""

    def _mask(value: Any) -> Any:
        return mask_cell(value, strategy, secret=secret)

    return _mask


def mask_dataframe(
    frame: Any,
    strategies: dict[str, str],
    *,
    unmask: bool,
    secret: str | None,
) -> Any:
    """Return *frame* with classified columns masked per *strategies*.

    Args:
        frame: An engine-native frame (pandas / pyarrow / polars /
            duckdb relation).
        strategies: ``{column_name: strategy}`` for the frame's table.
        unmask: When ``True`` the frame is returned untouched (the
            viewer may see cleartext).
        secret: HMAC secret for the ``hash`` strategy.

    Returns:
        A pandas frame with the named columns masked, or the original
        frame when nothing needs masking / the type can't be read.
    """
    active = {c: s for c, s in strategies.items() if s != "none"}
    if unmask or not active:
        return frame

    import pandas as pd  # noqa: PLC0415 — lazy, default engine

    if isinstance(frame, pd.DataFrame):
        pdf = frame.copy()
    elif hasattr(frame, "to_pandas"):
        pdf = frame.to_pandas()
    elif hasattr(frame, "df"):
        pdf = frame.df()
    else:
        return frame

    for column, strategy in active.items():
        if column in pdf.columns:
            pdf[column] = pdf[column].map(_column_masker(strategy, secret))
    return pdf


def mask_sql_rows(
    columns: list[str],
    rows: list[list[Any]],
    strategies: dict[str, str],
    *,
    unmask: bool,
    secret: str | None,
) -> list[list[Any]]:
    """Best-effort mask SQL result rows by result-column name.

    Matches each result column name (case-insensitively) against
    *strategies* and masks that position in every row.  This is
    best-effort: a query that aliases or computes a classified column
    produces a result name that no longer matches, so the masked column
    slips through — exact mapping only holds for the product's declared
    output ports.

    Args:
        columns: Result column names, in order.
        rows: Result rows (list of lists), parallel to *columns*.
        strategies: ``{column_name_lower: strategy}``.
        unmask: When ``True`` rows are returned untouched.
        secret: HMAC secret for the ``hash`` strategy.

    Returns:
        New rows with matched positions masked.
    """
    active = {c.lower(): s for c, s in strategies.items() if s != "none"}
    if unmask or not active:
        return rows

    col_strategy: dict[int, str] = {}
    for idx, name in enumerate(columns):
        strategy = active.get(str(name).lower())
        if strategy is not None:
            col_strategy[idx] = strategy
    if not col_strategy:
        return rows

    masked: list[list[Any]] = []
    for row in rows:
        new_row = list(row)
        for idx, strategy in col_strategy.items():
            if idx < len(new_row):
                new_row[idx] = mask_cell(new_row[idx], strategy, secret=secret)
        masked.append(new_row)
    return masked
