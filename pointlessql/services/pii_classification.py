"""Automatic PII classification: sample columns, tag what looks sensitive.

The scanner combines two signal sources per column: the column *name*
(``email``, ``phone``, ``iban`` …) and a regex pass over a small value
sample read straight from the Delta table.  A hit writes the column
tag ``pii=<kind>`` through the catalog facade — additively only: a
column that already carries a ``pii`` tag is never re-classified or
un-tagged, so human curation always wins over the heuristics.

Paired with a tag policy rule (``pii`` → ``mask``) this closes the
loop: newly detected sensitive columns are masked for everyone except
admins and the table owner without any per-table configuration.

Runs either interactively (admin "Scan now" in the classification
console) or on a schedule via the ``pii_classification`` job kind.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

PII_TAG_KEY = "pii"

# How many non-null values to sample per string column.
SAMPLE_ROWS = 50

# Fraction of sampled values that must match a value regex before the
# column is classified — a single email in a free-text column is not a
# signal.
MATCH_THRESHOLD = 0.6

# Column-name fragments → kind.  Checked on the lowercased name with
# non-alphanumerics stripped, so ``E_Mail`` and ``customerEmail`` both
# hit ``email``.
_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("email", "email"),
    ("mail", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("telefon", "phone"),
    ("iban", "iban"),
    ("creditcard", "card"),
    ("cardnumber", "card"),
    ("birthdate", "birthdate"),
    ("birthday", "birthdate"),
    ("dateofbirth", "birthdate"),
    ("geburtsdatum", "birthdate"),
    ("street", "address"),
    ("address", "address"),
    ("postcode", "address"),
    ("zipcode", "address"),
)

_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]{2,}$")),
    ("iban", re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")),
    ("card", re.compile(r"^(?:\d[ -]?){13,19}$")),
    ("phone", re.compile(r"^\+?[\d ()/-]{7,20}$")),
)

# String-ish Delta/Arrow type names eligible for value sampling.
_STRINGY = ("string", "varchar", "utf8", "text", "large_string")


@dataclass(frozen=True)
class Finding:
    """One classified column."""

    table: str
    column: str
    kind: str
    source: str  # "name" | "values"
    applied: bool


def classify_name(column: str) -> str | None:
    """Classify a column purely by its name.

    Args:
        column: The raw column name.

    Returns:
        The PII kind, or ``None`` when the name carries no hint.
    """
    normalised = re.sub(r"[^a-z0-9]", "", column.lower())
    for fragment, kind in _NAME_HINTS:
        if fragment in normalised:
            return kind
    return None


def classify_values(samples: list[str]) -> str | None:
    """Classify a column by its sampled values.

    Args:
        samples: Non-null stringified sample values.

    Returns:
        The PII kind whose pattern matches at least
        :data:`MATCH_THRESHOLD` of the samples, or ``None``.
    """
    cleaned = [s.strip() for s in samples if isinstance(s, str) and s.strip()]
    if len(cleaned) < 3:
        return None
    for kind, pattern in _VALUE_PATTERNS:
        hits = sum(1 for value in cleaned if pattern.match(value))
        if hits / len(cleaned) >= MATCH_THRESHOLD:
            return kind
    return None


def _sample_column(storage_location: str, full_name: str, column: str) -> list[str]:
    """Read up to :data:`SAMPLE_ROWS` non-null values of one column.

    Args:
        storage_location: Delta table path.
        full_name: Three-part name (view registration identifier).
        column: Column to sample.

    Returns:
        Stringified sample values; empty on any read problem (the
        scanner then falls back to name-only classification).
    """
    import duckdb

    from pointlessql.pql.engine import register_delta_view

    try:
        conn = duckdb.connect()
        try:
            register_delta_view(conn, full_name, storage_location)
            quoted = column.replace('"', '""')
            rows = conn.execute(
                f'SELECT "{quoted}" FROM "{full_name}" '
                f'WHERE "{quoted}" IS NOT NULL LIMIT {SAMPLE_ROWS}'
            ).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — sampling is best-effort
        logger.debug("pii scan: sampling %s.%s failed", full_name, column, exc_info=True)
        return []
    return [str(r[0]) for r in rows]


async def scan_table(uc_client: Any, full_name: str) -> list[Finding]:
    """Scan one table and tag newly classified columns.

    Args:
        uc_client: Principal-bound catalog facade.
        full_name: Three-part table name.

    Returns:
        One :class:`Finding` per classified column.  ``applied`` is
        ``False`` when the column already carried a ``pii`` tag (human
        curation wins) or the tag write failed.
    """
    parts = full_name.split(".")
    if len(parts) != 3:
        return []
    info = await uc_client.get_table(parts[0], parts[1], parts[2])
    if not info:
        return []
    storage = info.get("storage_location")
    findings: list[Finding] = []
    for col in info.get("columns") or []:
        if not isinstance(col, dict):
            continue
        name = str(col.get("name") or "")
        if not name:
            continue
        col_type = str(col.get("type_text") or col.get("type_name") or col.get("type") or "")
        kind = classify_name(name)
        source = "name"
        if kind is None and storage and any(t in col_type.lower() for t in _STRINGY):
            kind = classify_values(_sample_column(str(storage), full_name, name))
            source = "values"
        if kind is None:
            continue
        existing = await uc_client.get_tags("column", f"{full_name}.{name}")
        already = any(
            isinstance(t, dict) and str(t.get("key", "")).lower() == PII_TAG_KEY
            for t in (existing or [])
        )
        applied = False
        if not already:
            try:
                await uc_client.update_tags(
                    "column",
                    f"{full_name}.{name}",
                    [{"key": PII_TAG_KEY, "op": "set", "value": kind}],
                )
                applied = True
            except Exception:  # noqa: BLE001 — keep scanning the rest
                logger.warning(
                    "pii scan: tag write failed for %s.%s", full_name, name, exc_info=True
                )
        findings.append(
            Finding(table=full_name, column=name, kind=kind, source=source, applied=applied)
        )
    return findings


async def scan_scope(
    uc_client: Any,
    *,
    table: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
) -> list[Finding]:
    """Scan one table or every table of a schema.

    Args:
        uc_client: Principal-bound catalog facade.
        table: Three-part name for a single-table scan.
        catalog: Catalog for a schema-wide scan.
        schema: Schema for a schema-wide scan.

    Returns:
        Findings across every scanned table.

    Raises:
        ValueError: When neither a table nor a catalog+schema pair is
            given.
    """
    if table:
        return await scan_table(uc_client, table)
    if not catalog or not schema:
        raise ValueError("scan needs either table=… or catalog=… and schema=…")
    findings: list[Finding] = []
    for info in await uc_client.list_tables(catalog, schema):
        name = info.get("name")
        if not name:
            continue
        findings.extend(await scan_table(uc_client, f"{catalog}.{schema}.{name}"))
    return findings


async def pii_classification_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: Any,
) -> None:
    """Scheduler executor for the ``pii_classification`` job kind.

    Config carries either ``{"table": "cat.sch.tbl"}`` or
    ``{"catalog": ..., "schema": ...}``.  Every finding lands as a job
    log line so the run detail page documents what was tagged.

    Args:
        job_run_id: Owning run (log correlation).
        user_info: Run-as principal (unused beyond the client the
            caller already bound).
        config: Scan scope.
        uc_client: Principal-bound catalog facade.

    Raises:
        ValueError: When the config carries no usable scope.
    """
    del user_info
    from pointlessql.db import get_session_factory
    from pointlessql.services.scheduler.runs._db import log_job

    findings = await scan_scope(
        uc_client,
        table=config.get("table"),
        catalog=config.get("catalog"),
        schema=config.get("schema"),
    )
    factory = get_session_factory()
    for f in findings:
        verb = "tagged" if f.applied else "found (already curated)"
        log_job(
            factory,
            job_run_id,
            None,
            "INFO",
            f"pii scan: {verb} {f.table}.{f.column} as {f.kind} (via {f.source})",
        )
    log_job(factory, job_run_id, None, "INFO", f"pii scan finished: {len(findings)} finding(s)")
