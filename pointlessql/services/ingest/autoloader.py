"""Auto-loader pull path — incremental file discovery + per-file append.

The regular file-based pull re-reads the whole configured path / glob
on every run and overwrites the target.  The auto-loader path instead
discovers which files are *new* (glob minus the
``autoloader_files`` registry), appends each one to the mapping's
Delta target via the same PQL write plane the full pull uses, and
records the file in the registry only after its append landed.

Semantics are **at-least-once** per file: a failure mid-pull stops the
loop and leaves the failing file unregistered, so the next pull
retries it — a crash between the Delta append and the registry insert
therefore re-appends that one file.  Exactly-once would need a
content-hash checkpoint like :func:`pointlessql.pql.autoload`'s; the
ingest surface keeps the cheaper path-keyed registry.

Discovery is **local-filesystem only** for now (``pathlib`` /
``glob``).  The ``parquet_glob`` connector hands its pattern straight
to DuckDB which can expand ``s3://`` globs server-side, but that gives
no file listing back — enumerating S3 objects for the registry needs
an object-store listing client and stays a follow-up.  ``s3`` /
``http`` sources therefore reject ``pull_mode="auto_loader"``.
"""

from __future__ import annotations

import datetime
import glob
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models.autoloader import AutoloaderFile
from pointlessql.services.ingest.connectors import build_reader_spec
from pointlessql.services.ingest.pull import PullError

logger = logging.getLogger(__name__)

# Mapping-level pull-mode values.  The key is OPTIONAL on the mapping
# dict — absence (or "full_reload") keeps the regular pull path, so
# only "auto_loader" is ever persisted.
AUTOLOADER_PULL_MODE = "auto_loader"
INGEST_FILE_PULL_MODES: tuple[str, ...] = ("full_reload", AUTOLOADER_PULL_MODE)

# Connector kinds whose configured path/pattern is locally globbable.
AUTOLOADER_KINDS: tuple[str, ...] = ("file_upload", "parquet_glob")

# Extensions the per-file DuckDB reader supports — mirrors the
# extension switch in ``connectors._file_reader_for_path``.
_SUPPORTED_SUFFIXES: tuple[str, ...] = (".csv", ".parquet", ".json", ".jsonl", ".ndjson")


@dataclass(frozen=True, slots=True)
class AutoloaderPullResult:
    """Outcome of one auto-loader mapping pull.

    Shape-compatible with
    :class:`pointlessql.services.ingest.pull.PullResult` where the
    executor consumes it (``target_fqn`` / ``rows_written`` /
    ``duration_ms`` / ``new_high_water_value`` / ``to_dict``), plus
    the per-file counter the auto-loader adds.

    Attributes:
        target_fqn: The Delta table the new files were appended to.
        files_processed: Number of newly-discovered files appended.
        rows_written: Total rows across all appended files.
        duration_ms: Wall-clock pull duration.
        new_high_water_value: Always ``None`` — the registry, not a
            watermark column, carries the incremental state.
        mode: Always ``"auto_loader"`` so run stats are
            distinguishable from full / incremental pulls.
    """

    target_fqn: str
    files_processed: int
    rows_written: int
    duration_ms: int
    new_high_water_value: str | None = None
    mode: str = AUTOLOADER_PULL_MODE

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict for the API response."""
        return {
            "target_fqn": self.target_fqn,
            "files_processed": int(self.files_processed),
            "rows_written": int(self.rows_written),
            "duration_ms": int(self.duration_ms),
            "new_high_water_value": self.new_high_water_value,
            "mode": self.mode,
        }


def pattern_for_kind(kind: str, config: dict[str, Any]) -> str:
    """Return the globbable path/pattern a file-based source configures.

    Args:
        kind: Connector kind.
        config: The source's non-secret config dict.

    Returns:
        The local path or glob pattern to discover files under.

    Raises:
        ValidationError: When *kind* is not auto-loader capable or the
            config key is missing.
    """
    if kind == "file_upload":
        pattern = str(config.get("path") or "").strip()
    elif kind == "parquet_glob":
        pattern = str(config.get("pattern") or "").strip()
    else:
        raise ValidationError(
            f"pull_mode='auto_loader' is not supported for kind {kind!r} — "
            f"only local file kinds {AUTOLOADER_KINDS} can be discovered incrementally. "
            "S3/HTTP discovery is a follow-up."
        )
    if not pattern:
        raise ValidationError(f"{kind} source has no path/pattern configured.")
    if "://" in pattern:
        raise ValidationError(
            "auto_loader discovery only supports local filesystem paths — "
            f"got {pattern!r}. S3/HTTP discovery is a follow-up."
        )
    return pattern


def _list_matching_files(pattern: str) -> list[str]:
    """Expand *pattern* to the sorted list of readable local files.

    A pattern containing glob characters is expanded with
    ``glob.glob(recursive=True)``; a plain file path yields itself; a
    directory is walked recursively.  Only files whose extension the
    per-file DuckDB reader supports are kept, and ordering is sorted
    so discover → append → register is reproducible across runs.

    Args:
        pattern: Local path, directory, or glob pattern.

    Returns:
        Sorted absolute file paths.
    """
    if any(ch in pattern for ch in ("*", "?", "[")):
        candidates = sorted(p for p in glob.glob(pattern, recursive=True) if Path(p).is_file())
    else:
        root = Path(pattern)
        if root.is_file():
            candidates = [str(root)]
        elif root.is_dir():
            candidates = sorted(str(p) for p in root.rglob("*") if p.is_file())
        else:
            candidates = []
    return [p for p in candidates if Path(p).suffix.lower() in _SUPPORTED_SUFFIXES]


def discover_new_files(
    factory: sessionmaker[Session],
    *,
    source_id: int,
    mapping_index: int,
    pattern: str,
) -> list[str]:
    """List files matching *pattern* that the registry has not seen.

    Args:
        factory: SQLAlchemy session factory for the metadata DB.
        source_id: Owning ``IngestSource`` primary key.
        mapping_index: Position inside the source's ``table_mappings``.
        pattern: Local path, directory, or glob pattern.

    Returns:
        Sorted file paths present on disk but absent from the
        ``autoloader_files`` registry for this ``(source, mapping)``.
    """
    candidates = _list_matching_files(pattern)
    if not candidates:
        return []
    with factory() as session:
        seen = set(
            session.scalars(
                select(AutoloaderFile.file_path).where(
                    AutoloaderFile.ingest_source_id == int(source_id),
                    AutoloaderFile.mapping_index == int(mapping_index),
                )
            ).all()
        )
    return [p for p in candidates if p not in seen]


def mark_processed(
    factory: sessionmaker[Session],
    *,
    source_id: int,
    mapping_index: int,
    paths: list[str],
) -> int:
    """Record *paths* as processed for one ``(source, mapping)`` pair.

    Idempotent via check-before-insert — paths already registered are
    skipped, so retrying a partially-marked batch is safe.  File size
    and mtime are captured best-effort; a file deleted between append
    and stat still registers (with NULL size/mtime) so it is not
    re-pulled.

    Args:
        factory: SQLAlchemy session factory for the metadata DB.
        source_id: Owning ``IngestSource`` primary key.
        mapping_index: Position inside the source's ``table_mappings``.
        paths: File paths to register.

    Returns:
        Number of registry rows actually inserted.
    """
    if not paths:
        return 0
    now = datetime.datetime.now(datetime.UTC)
    inserted = 0
    with factory() as session:
        existing = set(
            session.scalars(
                select(AutoloaderFile.file_path).where(
                    AutoloaderFile.ingest_source_id == int(source_id),
                    AutoloaderFile.mapping_index == int(mapping_index),
                    AutoloaderFile.file_path.in_(paths),
                )
            ).all()
        )
        for path in paths:
            if path in existing:
                continue
            size: int | None = None
            mtime: datetime.datetime | None = None
            try:
                stat = Path(path).stat()
                size = int(stat.st_size)
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.UTC)
            except OSError:
                logger.debug("autoloader: stat failed for %s; registering without size", path)
            session.add(
                AutoloaderFile(
                    ingest_source_id=int(source_id),
                    mapping_index=int(mapping_index),
                    file_path=path,
                    file_size=size,
                    file_mtime=mtime,
                    processed_at=now,
                )
            )
            inserted += 1
        session.commit()
    return inserted


def _read_file_frame(path: str) -> Any:
    """Read one local file into a pandas DataFrame via DuckDB.

    Reuses the connector plane's reader selection
    (:func:`pointlessql.services.ingest.connectors.build_reader_spec`
    with a single-path ``file_upload`` config) so the auto-loader
    types columns exactly like a full pull of the same file would.

    Args:
        path: Local file path with a supported extension.

    Returns:
        The pandas frame DuckDB materialised.

    Raises:
        PullError: When no reader exists for the extension or the
            read itself fails.
    """
    try:
        spec = build_reader_spec("file_upload", {"path": path})
    except ValidationError as exc:
        raise PullError(reason=str(exc)) from exc
    conn = duckdb.connect(":memory:")
    try:
        return conn.execute(spec.sql).fetch_df()
    except duckdb.Error as exc:
        logger.warning("autoloader read failed for %s: %s", path, exc)
        raise PullError(
            reason=f"Could not read {path!r}.",
            hint="See server logs for the underlying DuckDB error.",
        ) from exc
    finally:
        conn.close()


def pull_incremental(
    factory: sessionmaker[Session],
    *,
    source_id: int,
    mapping_index: int,
    kind: str,
    config: dict[str, Any],
    mapping: dict[str, Any],
    pql_instance: Any,
) -> AutoloaderPullResult:
    """Append every newly-discovered file to the mapping's target.

    Files are processed in sorted order; each successful append is
    registered immediately, so a failure on file N keeps files 1..N-1
    out of the next pull.  The failing file itself stays unregistered
    (at-least-once — its partial append, if any, is re-applied on
    retry).

    Args:
        factory: SQLAlchemy session factory for the metadata DB.
        source_id: Owning ``IngestSource`` primary key.
        mapping_index: Position inside the source's ``table_mappings``.
        kind: Connector kind (must be auto-loader capable).
        config: The source's resolved non-secret config.
        mapping: The mapping dict (provides ``target_fqn``).
        pql_instance: A :class:`pointlessql.pql.pql.PQL` instance —
            caller-owned so tests can inject a fixture, mirroring
            :func:`pointlessql.services.ingest.pull.pull_mapping`.

    Returns:
        An :class:`AutoloaderPullResult` with file + row counters.

    Raises:
        PullError: On an unsupported kind/pattern, a file read
            failure, or a Delta append failure.  Processing stops at
            the first failing file.
    """
    started = time.perf_counter()
    target_fqn = str(mapping.get("target_fqn") or "").strip()
    if not target_fqn or target_fqn.count(".") != 2:
        raise PullError(reason=f"target_fqn must be 'catalog.schema.table', got {target_fqn!r}.")
    try:
        pattern = pattern_for_kind(kind, config)
    except ValidationError as exc:
        raise PullError(reason=str(exc)) from exc

    new_files = discover_new_files(
        factory, source_id=source_id, mapping_index=mapping_index, pattern=pattern
    )

    files_processed = 0
    rows_written = 0
    for path in new_files:
        df = _read_file_frame(path)
        try:
            pql_instance.write_table(df, target_fqn, mode="append")
        except Exception as exc:  # noqa: BLE001 — surface as PullError
            logger.exception("autoloader append failed for %s", path)
            raise PullError(
                reason=f"Append of {path!r} to {target_fqn} failed: {type(exc).__name__}.",
                hint="The file stays unregistered and is retried on the next pull.",
            ) from exc
        mark_processed(factory, source_id=source_id, mapping_index=mapping_index, paths=[path])
        files_processed += 1
        rows_written += int(getattr(df, "shape", (0, 0))[0])

    duration_ms = int((time.perf_counter() - started) * 1000)
    return AutoloaderPullResult(
        target_fqn=target_fqn,
        files_processed=files_processed,
        rows_written=rows_written,
        duration_ms=duration_ms,
    )
