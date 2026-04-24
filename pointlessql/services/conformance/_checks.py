"""Per-layer conformance checks against the Sprint-13.5.1 conventions.

Findings are shaped for direct rendering — the run-detail view
groups them by table and shows the ``severity`` as a colored
badge with the ``message`` as tooltip.  Severities are graded so
a reviewer can sort attention: ``error`` for a hard contract
violation (bronze missing audit columns), ``warning`` for soft
hints (silver without an obvious dedup key), ``info`` for
context (gold appears wide).

The audit list deliberately stays bronze-centric in the MVP —
silver and gold violations are easier to false-positive on
without table-content inspection, so we surface them as gentle
hints and let the operator interpret.
"""

from __future__ import annotations

from dataclasses import dataclass

from pointlessql.conventions import ConventionsConfig


@dataclass(frozen=True)
class ConformanceFinding:
    """One conformance finding for one table.

    ``table_full_name`` is the UC ``catalog.schema.table`` string
    so the template can group findings by table.  ``layer`` is the
    inferred Medallion layer (``bronze`` / ``silver`` / ``gold``)
    or ``None`` if no layer matched — None-layer tables are
    rendered with no badges at all (passive principle).

    Attributes:
        table_full_name: ``catalog.schema.table`` reference.
        layer: Inferred layer name, or ``None``.
        severity: ``error`` / ``warning`` / ``info``.
        code: Short stable identifier (``bronze.missing_audit_column``).
        message: Human-readable explanation for the badge tooltip.
    """

    table_full_name: str
    layer: str | None
    severity: str
    code: str
    message: str


def infer_layer_from_full_name(
    full_name: str, conventions: ConventionsConfig
) -> str | None:
    """Return the Medallion layer name a table belongs to, or ``None``.

    The MVP heuristic matches on the schema-name (middle component
    of the 3-part name) against the configured layer names.  If
    schema is ``bronze``, the table is bronze; if ``silver``,
    silver; if ``gold``, gold.  Anything else → ``None`` (no
    layer, no checks).

    Operators who use different schema names today can land on
    the convention by either (a) renaming their schemas, or (b)
    waiting for the Sprint-13.5.1 ``layer_tag_key`` UC-tag hook
    to be wired through the soyuz client (currently MVP-deferred).

    Args:
        full_name: Three-part UC name ``catalog.schema.table``.
        conventions: Loaded :class:`ConventionsConfig` with the
            layer-name list.

    Returns:
        The matching layer name, or ``None``.
    """
    parts = full_name.split(".")
    if len(parts) != 3:
        return None
    schema = parts[1]
    for layer in conventions.layers:
        if layer.name == schema:
            return layer.name
    return None


def check_table_against_layer(
    *,
    table_full_name: str,
    layer: str | None,
    column_names: list[str],
    conventions: ConventionsConfig,
) -> list[ConformanceFinding]:
    """Apply the layer's conformance checks to *column_names*.

    Bronze: every required audit column from the conventions must
    appear in the table.  Missing audit columns are ``error``-level
    findings — they break the provenance contract.

    Silver: an info-level hint when none of the SCD-2 column names
    (``_valid_from`` / ``_valid_to`` / ``_is_current``) and no
    ``id`` / ``key``-suffixed column appear, on the assumption
    that *some* deduplication anchor should be visible.  Soft
    heuristic; tolerated as ``info`` rather than ``warning``.

    Gold: an info-level hint when the table has more than 50
    columns — that's wide enough to suggest a fact table is
    sneaking in raw dimensions.  Pure visibility, not a
    violation.

    Args:
        table_full_name: ``catalog.schema.table`` reference (only
            used for finding identity).
        layer: ``"bronze"`` / ``"silver"`` / ``"gold"``, or
            ``None`` for tables outside the convention.
        column_names: All column names on the table.
        conventions: Loaded conventions.

    Returns:
        List of findings.  Empty when the table conforms or no
        layer was inferred.
    """
    if layer is None:
        return []

    layer_def = conventions.get_layer(layer)
    if layer_def is None:
        return []

    column_set = set(column_names)
    findings: list[ConformanceFinding] = []

    if layer == "bronze":
        for required in layer_def.required_audit_columns:
            if required not in column_set:
                findings.append(
                    ConformanceFinding(
                        table_full_name=table_full_name,
                        layer="bronze",
                        severity="error",
                        code="bronze.missing_audit_column",
                        message=(
                            f"Bronze table is missing the required audit "
                            f"column ``{required}`` — provenance is broken "
                            "for new appends."
                        ),
                    )
                )
        return findings

    if layer == "silver":
        scd2_present = any(
            c in column_set for c in ("_valid_from", "_valid_to", "_is_current")
        )
        key_present = any(
            c.endswith("_id") or c == "id" or c.endswith("_key") or c == "key"
            for c in column_names
        )
        if not (scd2_present or key_present):
            findings.append(
                ConformanceFinding(
                    table_full_name=table_full_name,
                    layer="silver",
                    severity="info",
                    code="silver.no_dedup_anchor",
                    message=(
                        "Silver table has no SCD-2 columns and no obvious "
                        "id/key column — confirm dedup is happening "
                        "upstream."
                    ),
                )
            )
        return findings

    if layer == "gold":
        if len(column_names) > 50:
            findings.append(
                ConformanceFinding(
                    table_full_name=table_full_name,
                    layer="gold",
                    severity="info",
                    code="gold.wide_table",
                    message=(
                        f"Gold table has {len(column_names)} columns — "
                        "consider whether dimensions should split into "
                        "their own tables."
                    ),
                )
            )
        return findings

    return findings
