"""Behaviour tests targeting surviving mutants in declared-consumption.

Pins the exact observable outputs of the consumption-verdict resolver
and its helpers: the declared-upstream query filters, the source-FQN
split, every field of the returned :class:`ConsumptionDecision`, and
the message surfaced on a strict-mode violation.  Each test asserts a
value that a surviving mutant would change.
"""

from __future__ import annotations

import datetime

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProductInputPort
from pointlessql.services.governance._consumption import (
    ConsumptionDecision,
    ConsumptionVerdict,
    ConsumptionViolation,
    _normalise_source,
    assert_declared_consumption,
    evaluate_consumption,
)


def _factory():
    return app.state.session_factory


def _add_port(product_id: int, *, name: str, kind: str, source_ref: str) -> None:
    """Insert one input-port row for a product."""
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=product_id,
                name=name,
                kind=kind,
                source_ref=source_ref,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# _normalise_source — table segment split + error message
# ---------------------------------------------------------------------------


def test_normalise_source_joins_extra_segments_with_dot() -> None:
    # A four-part name keeps the trailing segments joined by a literal
    # dot, not a placeholder, and includes every segment from index 2.
    assert _normalise_source("cat.sch.tbl.part") == ("cat", "sch", "tbl.part")


def test_normalise_source_two_part_has_no_table() -> None:
    assert _normalise_source("cat.sch") == ("cat", "sch", None)


def test_normalise_source_three_part_keeps_full_table() -> None:
    assert _normalise_source("cat.sch.tbl") == ("cat", "sch", "tbl")


def test_normalise_source_single_segment_raises_with_message() -> None:
    # A one-part name is invalid; the raised error carries a real
    # diagnostic message (not a bare None).
    with pytest.raises(ValueError, match="must be catalog.schema"):
        _normalise_source("lonely")


# ---------------------------------------------------------------------------
# _is_declared_upstream — each WHERE filter must narrow the match
# ---------------------------------------------------------------------------


def test_declared_check_is_scoped_to_the_consumer_product() -> None:
    # A matching port that belongs to a DIFFERENT product must not make
    # this consumer's read count as declared.
    other_product = 4242
    consumer = 4243
    _add_port(
        other_product,
        name="up",
        kind="upstream_product",
        source_ref="cat.sch",
    )
    decision = evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.declared is False
    assert decision.verdict is ConsumptionVerdict.WARN


def test_declared_check_requires_upstream_product_kind() -> None:
    # A port with the same product + source_ref but a non-upstream kind
    # is not a declared upstream input.
    consumer = 4244
    _add_port(
        consumer,
        name="ext",
        kind="external",
        source_ref="cat.sch",
    )
    decision = evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.declared is False
    assert decision.verdict is ConsumptionVerdict.WARN


def test_declared_check_requires_matching_source_ref() -> None:
    # A correctly-typed upstream port on the right product, but pointing
    # at a different source, must not satisfy this read.
    consumer = 4245
    _add_port(
        consumer,
        name="up",
        kind="upstream_product",
        source_ref="cat.other",
    )
    decision = evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.declared is False
    assert decision.verdict is ConsumptionVerdict.WARN


def test_declared_check_allows_exact_upstream_match() -> None:
    # The positive control: product + kind + schema-grained source all
    # line up, so the read is declared and allowed.
    consumer = 4246
    _add_port(
        consumer,
        name="up",
        kind="upstream_product",
        source_ref="cat.sch",
    )
    decision = evaluate_consumption(
        _factory(),
        mode="strict",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.declared is True
    assert decision.verdict is ConsumptionVerdict.ALLOW
    assert decision.reason == "declared"


# ---------------------------------------------------------------------------
# evaluate_consumption — ALLOW branch field provenance (off mode)
# ---------------------------------------------------------------------------


def test_evaluate_off_mode_allows_with_full_provenance() -> None:
    # With enforcement off and nothing declared, the ALLOW decision must
    # echo mode / consumer / source verbatim and use the off-mode reason.
    consumer = 5001
    decision = evaluate_consumption(
        _factory(),
        mode="off",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.verdict is ConsumptionVerdict.ALLOW
    assert decision.mode == "off"
    assert decision.consumer_product_id == consumer
    assert decision.source_fqn == "cat.sch.tbl"
    assert decision.declared is False
    assert decision.reason == "enforcement off"


def test_evaluate_declared_match_reports_declared_reason() -> None:
    # The declared-allow branch carries the literal "declared" reason and
    # the real mode through (not None).
    consumer = 5002
    _add_port(
        consumer,
        name="up",
        kind="upstream_product",
        source_ref="cat.sch",
    )
    decision = evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.verdict is ConsumptionVerdict.ALLOW
    assert decision.mode == "advisory"
    assert decision.consumer_product_id == consumer
    assert decision.source_fqn == "cat.sch.tbl"
    assert decision.declared is True
    assert decision.reason == "declared"


# ---------------------------------------------------------------------------
# evaluate_consumption — WARN / BLOCK branch fields
# ---------------------------------------------------------------------------


def test_evaluate_advisory_warn_fields() -> None:
    consumer = 5003
    decision = evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.verdict is ConsumptionVerdict.WARN
    # The undeclared WARN must explicitly stamp declared=False (an
    # identity check distinguishes a None mutant from False).
    assert decision.declared is False
    assert decision.reason == "cat.sch is not a declared input-port"


def test_evaluate_strict_block_carries_reason() -> None:
    consumer = 5004
    decision = evaluate_consumption(
        _factory(),
        mode="strict",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.verdict is ConsumptionVerdict.BLOCK
    assert decision.mode == "strict"
    # The block reason names the schema-grained source, not a bare None.
    assert decision.reason == "cat.sch is not a declared input-port"


# ---------------------------------------------------------------------------
# assert_declared_consumption — call-site threads the consumer id
# ---------------------------------------------------------------------------


def test_assert_declared_consumption_passes_consumer_id_through() -> None:
    # The wrapper must forward the real consumer id to the evaluator; a
    # mutant passing None would surface a None on the returned decision.
    consumer = 6001
    decision = assert_declared_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="cat.sch.tbl",
    )
    assert decision.consumer_product_id == consumer
    assert decision.verdict is ConsumptionVerdict.WARN


def test_assert_declared_consumption_raises_on_block() -> None:
    consumer = 6002
    with pytest.raises(ConsumptionViolation) as exc:
        assert_declared_consumption(
            _factory(),
            mode="strict",
            consumer_product_id=consumer,
            source_fqn="cat.sch.tbl",
        )
    assert exc.value.decision.consumer_product_id == consumer
    assert exc.value.decision.verdict is ConsumptionVerdict.BLOCK


# ---------------------------------------------------------------------------
# ConsumptionViolation.__init__ — propagates the decision reason
# ---------------------------------------------------------------------------


def test_consumption_violation_detail_is_the_decision_reason() -> None:
    decision = ConsumptionDecision(
        verdict=ConsumptionVerdict.BLOCK,
        mode="strict",
        consumer_product_id=9,
        source_fqn="cat.sch.tbl",
        declared=False,
        reason="cat.sch is not a declared input-port",
    )
    violation = ConsumptionViolation(decision)
    # The base error message must be the decision's reason, not None.
    assert violation.detail == "cat.sch is not a declared input-port"
    assert str(violation) == "cat.sch is not a declared input-port"
    assert violation.decision is decision
