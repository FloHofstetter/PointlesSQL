"""Hypothesis strategies for the SQL-parser reference-extraction suite.

Builds valid three-part UC table references — with identifier edge cases:
quoted names, reserved words, and embedded dots / spaces — and assembles
them into SELECT / JOIN / CTE / subquery statements plus INSERT…SELECT
writes, each paired with the references the parser is expected to
enumerate.  Every identifier segment is always double-quoted so a reserved
word or a name with a dot/space is unambiguous to the parser, and the
expected FQN is computed exactly as the parser computes it
(:meth:`TableFqn.from_parts`), so the strategy and the parser agree on
what a reference string is.
"""

from __future__ import annotations

from typing import NamedTuple

from hypothesis import strategies as st

from pointlessql.types import TableFqn


class Table(NamedTuple):
    """A generated three-part table: its FQN string and its quoted SQL token."""

    fqn: str
    sql: str


_RESERVED = ("select", "from", "where", "table", "order", "group", "join", "by")
_SIMPLE = ("orders", "customers", "events", "t1", "t2", "users", "x")
# Names that MUST be quoted: embedded space, embedded dot(s).
_TRICKY = ("my col", "a.b", "weird name", "c.d.e")

_ATOM = st.one_of(
    st.sampled_from(_SIMPLE),
    st.sampled_from(_RESERVED),
    st.sampled_from(_TRICKY),
    st.from_regex(r"[a-z][a-z0-9_]{0,7}", fullmatch=True),
)

# A conservative atom for CTE aliases — plain identifiers only, so the
# shadowing construction stays unambiguous.
_ALIAS = st.sampled_from(_SIMPLE)


def _quote(raw: str) -> str:
    """Render *raw* as an always-quoted SQL identifier (dialect-safe)."""
    return '"' + raw + '"'


def _first_seen(items: list[str]) -> list[str]:
    """Deduplicate *items* preserving first-appearance order."""
    return list(dict.fromkeys(items))


@st.composite
def table_strategy(draw: st.DrawFn) -> Table:
    """Draw one fully-qualified three-part table reference."""
    catalog = draw(_ATOM)
    schema = draw(_ATOM)
    name = draw(_ATOM)
    fqn = str(TableFqn.from_parts(catalog, schema, name))
    sql = f"{_quote(catalog)}.{_quote(schema)}.{_quote(name)}"
    return Table(fqn=fqn, sql=sql)


@st.composite
def join_select(draw: st.DrawFn) -> tuple[str, list[str]]:
    """A SELECT over a JOIN chain (with possible repeats) + expected refs."""
    pool = draw(st.lists(table_strategy(), min_size=1, max_size=4, unique_by=lambda t: t.fqn))
    seq = draw(st.lists(st.sampled_from(pool), min_size=1, max_size=6))
    sql = "SELECT * FROM " + seq[0].sql + "".join(f" JOIN {t.sql} ON 1 = 1" for t in seq[1:])
    return sql, _first_seen([t.fqn for t in seq])


@st.composite
def subquery_select(draw: st.DrawFn) -> tuple[str, list[str]]:
    """A SELECT wrapping a derived-table subquery, joined to a table + refs."""
    inner = draw(table_strategy())
    outer = draw(table_strategy())
    sql = f"SELECT * FROM (SELECT * FROM {inner.sql}) sub JOIN {outer.sql} ON 1 = 1"
    return sql, _first_seen([inner.fqn, outer.fqn])


@st.composite
def cte_shadow_select(draw: st.DrawFn) -> tuple[str, list[str]]:
    """A CTE whose alias shadows a real table's bare name + expected refs.

    The bare ``FROM <alias>`` resolves to the CTE (and is skipped), while
    the three-part table whose final segment equals the alias is still a
    genuine reference — so the alias must never be counted as a table.
    """
    alias = draw(_ALIAS)
    catalog = draw(_ATOM)
    schema = draw(_ATOM)
    real_fqn = str(TableFqn.from_parts(catalog, schema, alias))
    real_sql = f"{_quote(catalog)}.{_quote(schema)}.{_quote(alias)}"
    sql = (
        f"WITH {_quote(alias)} AS (SELECT 1 AS x) "
        f"SELECT * FROM {_quote(alias)} JOIN {real_sql} ON 1 = 1"
    )
    return sql, [real_fqn]


@st.composite
def insert_select(draw: st.DrawFn) -> tuple[str, str, str]:
    """An INSERT…SELECT with distinct target + source; (sql, target, source)."""
    target = draw(table_strategy())
    source = draw(table_strategy().filter(lambda s: s.fqn != target.fqn))
    sql = f"INSERT INTO {target.sql} SELECT * FROM {source.sql}"
    return sql, target.fqn, source.fqn
