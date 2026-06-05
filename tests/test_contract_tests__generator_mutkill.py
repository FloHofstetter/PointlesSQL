"""Behaviour tests pinning the synthetic-data generator internals.

These tests assert exact error messages, captured ``random`` call
bounds, default-argument fallbacks, and branch outcomes for the Arrow
generator so that small mutations to literals, dict-key lookups, swap
logic, and comparison operators become observable failures.

Many tests drive :func:`_generate_value` directly with a stub
``random.Random`` so the otherwise-random ``lo``/``hi`` bounds become
deterministic and assertable.
"""

from __future__ import annotations

import datetime

import pytest
from faker import Faker

from pointlessql.services.contract_tests._generator import (
    _decode_spec,
    _generate_value,
    generate_arrow_table,
)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class _StubRnd:
    """Deterministic stand-in for ``random.Random``.

    Records the bounds passed to ``randint``/``uniform`` so default and
    keyed-lookup behaviour in the generator can be asserted directly,
    and lets ``random()`` be pinned to a chosen value.
    """

    def __init__(self, random_val: float = 0.0) -> None:
        self.random_val = random_val
        self.randint_args: tuple[int, int] | None = None
        self.uniform_args: tuple[float, float] | None = None
        self.randint_return: str = "low"  # which bound randint returns

    def randint(self, a: int, b: int) -> int:
        self.randint_args = (a, b)
        return a if self.randint_return == "low" else b

    def uniform(self, a: float, b: float) -> float:
        self.uniform_args = (a, b)
        return a

    def random(self) -> float:
        return self.random_val

    def choice(self, seq: list) -> object:
        return seq[0]


def _fake() -> Faker:
    fake = Faker()
    fake.seed_instance(0)
    return fake


# ---------------------------------------------------------------------------
# _decode_spec error messages
# ---------------------------------------------------------------------------


def test_decode_spec_non_dict_entry_message() -> None:
    # A non-dict list entry must raise with the exact wording; a None or
    # mangled message would not match.
    with pytest.raises(ValueError, match="each spec entry must be an object"):
        _decode_spec([{"column": "a", "kind": "int"}, 5])


def test_decode_spec_invalid_json_message() -> None:
    with pytest.raises(ValueError, match="spec is not valid JSON"):
        _decode_spec("{not json")


def test_decode_spec_non_list_json_message() -> None:
    with pytest.raises(ValueError, match="spec must be a JSON list"):
        _decode_spec('{"column": "a"}')


def test_decode_spec_non_list_message_exact_casing() -> None:
    # Pin the exact casing/wording so an upper/lower-cased mutant fails.
    with pytest.raises(ValueError) as exc:
        _decode_spec("123")
    assert str(exc.value) == "spec must be a JSON list"


def test_decode_spec_non_dict_entry_message_exact_casing() -> None:
    with pytest.raises(ValueError) as exc:
        _decode_spec(["x"])
    assert str(exc.value) == "each spec entry must be an object"


def test_decode_spec_invalid_json_message_is_not_none() -> None:
    with pytest.raises(ValueError) as exc:
        _decode_spec("[1, 2")
    assert str(exc.value) != "None"
    assert "spec is not valid JSON" in str(exc.value)


# ---------------------------------------------------------------------------
# _generate_value — int kind defaults / swap
# ---------------------------------------------------------------------------


def test_int_default_min_and_max_bounds() -> None:
    # No min/max => randint must be called with (0, 100); None/empty
    # defaults would crash on int(None), and 1/101 defaults would shift.
    rnd = _StubRnd()
    _generate_value("int", {}, rnd, _fake())
    assert rnd.randint_args == (0, 100)


def test_int_reads_min_key() -> None:
    rnd = _StubRnd()
    _generate_value("int", {"min": 5, "max": 9}, rnd, _fake())
    assert rnd.randint_args == (5, 9)


def test_int_min_greater_than_max_swaps_bounds() -> None:
    # min>max => the swap branch must run and produce (lo, hi) ordered.
    # A ``lo, hi = None`` mutant raises TypeError instead of swapping.
    rnd = _StubRnd()
    _generate_value("int", {"min": 10, "max": 2}, rnd, _fake())
    assert rnd.randint_args == (2, 10)


# ---------------------------------------------------------------------------
# _generate_value — float kind defaults / key lookup / swap
# ---------------------------------------------------------------------------


def test_float_default_min_and_max_bounds() -> None:
    # No min/max => uniform called with (0.0, 1.0).  None/empty defaults
    # would crash float(None); a 2.0 max default would widen the range.
    rnd = _StubRnd()
    _generate_value("float", {}, rnd, _fake())
    assert rnd.uniform_args == (0.0, 1.0)


def test_float_reads_min_key() -> None:
    # The lookup key must be literally "min"; a None/"MIN"/"XXminXX" key
    # would ignore the provided 0.9 and fall back to the 0.0 default.
    rnd = _StubRnd()
    _generate_value("float", {"min": 0.9, "max": 1.0}, rnd, _fake())
    assert rnd.uniform_args == (0.9, 1.0)


def test_float_reads_max_key() -> None:
    rnd = _StubRnd()
    _generate_value("float", {"min": 0.0, "max": 0.25}, rnd, _fake())
    assert rnd.uniform_args == (0.0, 0.25)


def test_float_min_greater_than_max_swaps_bounds() -> None:
    # min>max swap branch; a ``lo, hi = None`` mutant raises TypeError.
    rnd = _StubRnd()
    _generate_value("float", {"min": 1.0, "max": 0.0}, rnd, _fake())
    assert rnd.uniform_args == (0.0, 1.0)


# ---------------------------------------------------------------------------
# _generate_value — iso8601_ts bounds / direction
# ---------------------------------------------------------------------------


def test_iso_default_since_days_bound() -> None:
    # No since_days => default 30 => randint upper bound 30*86400.
    rnd = _StubRnd()
    _generate_value("iso8601_ts", {}, rnd, _fake())
    assert rnd.randint_args == (0, 30 * 86400)


def test_iso_reads_since_days_key() -> None:
    # The lookup key must be "since_days"; a renamed/None key would fall
    # back to 30 and ignore the provided 7.
    rnd = _StubRnd()
    _generate_value("iso8601_ts", {"since_days": 7}, rnd, _fake())
    assert rnd.randint_args == (0, 7 * 86400)


def test_iso_randint_lower_bound_is_zero() -> None:
    rnd = _StubRnd()
    _generate_value("iso8601_ts", {"since_days": 3}, rnd, _fake())
    assert rnd.randint_args is not None
    assert rnd.randint_args[0] == 0


def test_iso_since_days_zero_clamps_to_one_day() -> None:
    # since_days=0 => max(1, 0)=1 => upper bound 86400.  A max(2, ...)
    # mutant would clamp to 2 days.
    rnd = _StubRnd()
    _generate_value("iso8601_ts", {"since_days": 0}, rnd, _fake())
    assert rnd.randint_args == (0, 86400)


def test_iso_seconds_per_day_multiplier() -> None:
    # The multiplier must be exactly 86400; 86401 would shift the bound.
    rnd = _StubRnd()
    _generate_value("iso8601_ts", {"since_days": 2}, rnd, _fake())
    assert rnd.randint_args == (0, 2 * 86400)


def test_iso_moment_is_in_the_past() -> None:
    # now - timedelta => moment <= now.  A ``now + timedelta`` mutant
    # would put the moment in the future.
    rnd = _StubRnd(random_val=0.0)
    rnd.randint_return = "high"  # force a positive, non-zero delta
    iso = _generate_value("iso8601_ts", {"since_days": 5}, rnd, _fake())
    moment = datetime.datetime.fromisoformat(iso)
    assert moment < _now()


# ---------------------------------------------------------------------------
# _generate_value — choice / bool / unknown
# ---------------------------------------------------------------------------


def test_choice_empty_message() -> None:
    rnd = _StubRnd()
    with pytest.raises(ValueError) as exc:
        _generate_value("choice", {"choices": []}, rnd, _fake())
    assert str(exc.value) == "choice generator requires non-empty 'choices'"


def test_bool_boundary_is_strict_less_than() -> None:
    # random() == p_true must yield False (strict ``<``).  A ``<=`` mutant
    # would return True at the boundary.
    rnd = _StubRnd(random_val=0.3)
    assert _generate_value("bool", {"p_true": 0.3}, rnd, _fake()) is False


def test_bool_default_p_true_is_half() -> None:
    # No p_true => default 0.5.  random()=0.7 < 0.5 is False; a 1.5
    # default would make it True, and None/empty defaults crash float().
    rnd = _StubRnd(random_val=0.7)
    assert _generate_value("bool", {}, rnd, _fake()) is False


def test_bool_default_p_true_half_true_side() -> None:
    rnd = _StubRnd(random_val=0.4)
    assert _generate_value("bool", {}, rnd, _fake()) is True


def test_generate_value_unknown_kind_message() -> None:
    rnd = _StubRnd()
    with pytest.raises(ValueError) as exc:
        _generate_value("not_a_kind", {}, rnd, _fake())
    assert str(exc.value) == "unknown generator kind: not_a_kind"


# ---------------------------------------------------------------------------
# generate_arrow_table — row clamping
# ---------------------------------------------------------------------------


def test_zero_row_count_yields_empty_table() -> None:
    # max(0, ...) keeps row_count=0 at zero rows; a max(1, ...) mutant
    # would emit one row.
    table = generate_arrow_table([{"column": "n", "kind": "int"}], row_count=0)
    assert table.num_rows == 0


def test_row_count_capped_at_one_hundred_thousand() -> None:
    # The upper cap is exactly 100_000; a 100001 cap would emit one more.
    table = generate_arrow_table([{"column": "n", "kind": "int"}], row_count=100_001)
    assert table.num_rows == 100_000


# ---------------------------------------------------------------------------
# generate_arrow_table — seeding determinism
# ---------------------------------------------------------------------------


def test_faker_seeding_is_deterministic_for_fixed_seed() -> None:
    # fake.seed_instance(seed) must use the real seed, not None.  With
    # seed=0 the first faker email is a known fixed value; a None-seed
    # mutant would draw a random, almost-never-matching value.
    table = generate_arrow_table([{"column": "e", "kind": "email"}], row_count=1, seed=0)
    assert table["e"].to_pylist() == ["achang@example.org"]


# ---------------------------------------------------------------------------
# generate_arrow_table — column / kind extraction + validation
# ---------------------------------------------------------------------------


def test_missing_column_raises_needs_both_message() -> None:
    # No "column" => name defaults to "" (empty) => "needs both".  A None
    # or "XXXX" default would make name non-empty and skip the guard.
    with pytest.raises(ValueError) as exc:
        generate_arrow_table([{"kind": "int"}], row_count=2)
    assert str(exc.value) == "every spec entry needs both 'column' and 'kind'"


def test_missing_kind_raises_needs_both_message() -> None:
    # No "kind" => kind defaults to "" => "needs both".  A None/"XXXX"
    # default would instead reach the "unknown generator kind" branch.
    with pytest.raises(ValueError) as exc:
        generate_arrow_table([{"column": "a"}], row_count=2)
    assert str(exc.value) == "every spec entry needs both 'column' and 'kind'"


def test_empty_name_and_kind_both_present_uses_or_guard() -> None:
    # name present but kind empty: ``not name or not kind`` is True so the
    # "needs both" guard fires.  An ``and`` mutant would skip it and reach
    # the "unknown generator kind" branch with a different message.
    with pytest.raises(ValueError) as exc:
        generate_arrow_table([{"column": "a", "kind": "   "}], row_count=2)
    assert str(exc.value) == "every spec entry needs both 'column' and 'kind'"


def test_blank_column_with_valid_kind_still_needs_both() -> None:
    # Whitespace-only column strips to "" => guard fires even with a
    # valid kind, distinguishing the or/and branch.
    with pytest.raises(ValueError) as exc:
        generate_arrow_table([{"column": "  ", "kind": "int"}], row_count=2)
    assert str(exc.value) == "every spec entry needs both 'column' and 'kind'"


# ---------------------------------------------------------------------------
# Equivalent-mutant notes (no killing test possible)
# ---------------------------------------------------------------------------
#
# A skeptical second pass confirmed the following survivors are equivalent
# and intentionally have no test:
#
#   * int/float ``if hi < lo`` -> ``if hi <= lo``: the only changed input is
#     ``hi == lo``, where the extra swap ``lo, hi = hi, lo`` is a no-op, so
#     ``randint``/``uniform`` see identical bounds.
#   * choice default ``descriptor.get("choices", [])`` -> ``..., None)`` or a
#     dropped default: the trailing ``or []`` collapses both a ``None`` and a
#     missing key to ``[]``, so the resolved choices list is unchanged.
#   * ``generate_arrow_table`` signature defaults ``row_count=100`` /
#     ``seed=0`` -> ``101`` / ``1``: mutmut's trampoline reproduces the public
#     signature and forwards both as explicit kwargs, leaving the mutated
#     inner defaults as dead code.
