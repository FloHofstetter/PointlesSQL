"""Hypothesis strategies for valid lineage-bearing PQL pipelines.

Generates small *valid* DataFrames (a schema of safe business columns plus a
unique ``_lineage_row_id`` per row) so the harness can run them through real
PQL primitives and assert the recorded lineage satisfies every invariant.
Business-column identifiers start with a letter, so they can never collide
with the underscore-prefixed audit/lineage columns; values stay ASCII-
printable here (Unicode / NULL-key edge cases live in the golden corpus).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from hypothesis import strategies as st

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN

_COLUMN_TYPES = ("int", "float", "str")
_identifiers = st.from_regex(r"[a-z][a-z0-9_]{0,11}", fullmatch=True)
_printable = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=12,
)


@dataclass(frozen=True)
class WritePipeline:
    """A single lineage-bearing ``write_table`` op to verify."""

    frame: pd.DataFrame
    source_fqn: str
    table_name: str


def _column_values(draw: Any, kind: str, n: int) -> list[Any]:
    if kind == "int":
        return draw(st.lists(st.integers(-1_000_000, 1_000_000), min_size=n, max_size=n))
    if kind == "float":
        return draw(
            st.lists(
                st.floats(allow_nan=False, allow_infinity=False),
                min_size=n,
                max_size=n,
            )
        )
    return draw(st.lists(_printable, min_size=n, max_size=n))


@st.composite
def _schemas(draw: Any) -> list[tuple[str, str]]:
    names = draw(st.lists(_identifiers, min_size=1, max_size=4, unique=True))
    return [(name, draw(st.sampled_from(_COLUMN_TYPES))) for name in names]


@st.composite
def write_pipelines(draw: Any) -> WritePipeline:
    """Draw a valid lineage-bearing frame + source/target labels for write_table."""
    schema = draw(_schemas())
    n = draw(st.integers(min_value=1, max_value=12))
    data: dict[str, list[Any]] = {name: _column_values(draw, kind, n) for name, kind in schema}
    data[LINEAGE_ROW_ID_COLUMN] = [f"row-{i}" for i in range(n)]
    frame = pd.DataFrame(data)
    return WritePipeline(
        frame=frame,
        source_fqn=f"lv.bronze.{draw(_identifiers)}",
        table_name=draw(_identifiers),
    )
