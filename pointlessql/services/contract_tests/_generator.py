"""Faker-driven synthetic-data generator producing Arrow tables.

The generator is deterministic — calls with the same spec and the
same seed return identical rows.  Output is a :class:`pyarrow.Table`
so the runner can evaluate any of the six assertion kinds without
touching storage.

Spec shape — a list of per-column descriptors:

    [
      {"column": "email",    "kind": "email"},
      {"column": "age",      "kind": "int",     "min": 18, "max": 80},
      {"column": "joined",   "kind": "iso8601_ts", "since_days": 30},
      {"column": "score",    "kind": "float",   "min": 0.0, "max": 1.0},
      {"column": "tier",     "kind": "choice",  "choices": ["bronze", "silver", "gold"]},
    ]

Unknown kinds raise :class:`ValueError`; callers translate that into
HTTP 400 at the route layer.
"""

from __future__ import annotations

import datetime
import json
import random
from typing import Any

import pyarrow as pa
from faker import Faker

#: Generator kinds the surface understands.  Adding a kind requires
#: extending :func:`_generate_column` and bumping the spec docs.
GENERATOR_KINDS: tuple[str, ...] = (
    "email",
    "name",
    "int",
    "float",
    "iso8601_ts",
    "choice",
    "uuid",
    "bool",
)


def generate_arrow_table(
    spec_json: str | list[dict[str, Any]],
    *,
    row_count: int = 100,
    seed: int = 0,
) -> pa.Table:
    """Build a :class:`pyarrow.Table` from a generator spec.

    Args:
        spec_json: Either the raw JSON string from the DB or a
            decoded list of per-column descriptors.
        row_count: Number of rows to emit; capped at 100k to avoid
            accidentally generating a memory bomb in a route handler.
        seed: Deterministic seed for both Python ``random`` and Faker.

    Returns:
        Arrow Table with one column per spec entry.

    Raises:
        ValueError: When the spec is malformed or names an unknown
            generator kind.
    """
    spec = _decode_spec(spec_json)
    rows = max(0, min(int(row_count), 100_000))
    rnd = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)
    columns: dict[str, list[Any]] = {}
    for descriptor in spec:
        name = str(descriptor.get("column", "")).strip()
        kind = str(descriptor.get("kind", "")).strip()
        if not name or not kind:
            raise ValueError("every spec entry needs both 'column' and 'kind'")
        if kind not in GENERATOR_KINDS:
            raise ValueError(f"unknown generator kind: {kind}")
        columns[name] = [_generate_value(kind, descriptor, rnd, fake) for _ in range(rows)]
    return pa.table(columns or {})


def _decode_spec(spec_json: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the decoded spec list, validating shape."""
    if isinstance(spec_json, list):
        decoded = spec_json
    else:
        try:
            decoded = json.loads(spec_json)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise ValueError("spec must be a JSON list")
    out: list[dict[str, Any]] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            raise ValueError("each spec entry must be an object")
        out.append(entry)
    return out


def _generate_value(
    kind: str,
    descriptor: dict[str, Any],
    rnd: random.Random,
    fake: Faker,
) -> Any:
    """Produce one cell value for *kind*."""
    if kind == "email":
        return fake.email()
    if kind == "name":
        return fake.name()
    if kind == "int":
        lo = int(descriptor.get("min", 0))
        hi = int(descriptor.get("max", 100))
        if hi < lo:
            lo, hi = hi, lo
        return rnd.randint(lo, hi)
    if kind == "float":
        lo = float(descriptor.get("min", 0.0))
        hi = float(descriptor.get("max", 1.0))
        if hi < lo:
            lo, hi = hi, lo
        return rnd.uniform(lo, hi)
    if kind == "iso8601_ts":
        since_days = int(descriptor.get("since_days", 30))
        delta_seconds = rnd.randint(0, max(1, since_days) * 86400)
        moment = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=delta_seconds)
        return moment.isoformat()
    if kind == "choice":
        choices = list(descriptor.get("choices", []) or [])
        if not choices:
            raise ValueError("choice generator requires non-empty 'choices'")
        return rnd.choice(choices)
    if kind == "uuid":
        return fake.uuid4()
    if kind == "bool":
        return rnd.random() < float(descriptor.get("p_true", 0.5))
    raise ValueError(f"unknown generator kind: {kind}")
