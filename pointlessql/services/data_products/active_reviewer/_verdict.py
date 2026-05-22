"""Verdict dataclass + LLM-response parser for the active reviewer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VerdictSeverity = Literal["ok", "warn", "critical"]


@dataclass(frozen=True)
class ReviewVerdict:
    """Structured result of one active-reviewer LLM turn.

    Attributes:
        severity: Maps to :class:`AgentReview.severity` (``ok`` /
            ``warn`` / ``critical``).
        endorsement_type: ``verified-by-steward`` on green,
            ``under-review`` on yellow / red, or ``None`` when the
            steward chose to suppress endorsement writes.
        comment_md: Markdown body posted as a
            :class:`DataProductComment`.
        raw_response: The raw LLM text (kept for trace).
    """

    severity: VerdictSeverity
    endorsement_type: str | None
    comment_md: str
    raw_response: str


_VERDICT_TO_SEVERITY: dict[str, VerdictSeverity] = {
    "green": "ok",
    "yellow": "warn",
    "red": "critical",
}


def parse_review_result(text: str) -> ReviewVerdict:
    """Parse one LLM response into a :class:`ReviewVerdict`.

    Looks for an explicit ``## Verdict: green | yellow | red`` line
    near the bottom.  Falls back to a keyword heuristic when the
    explicit marker is absent.

    Args:
        text: Raw LLM response body.

    Returns:
        A populated :class:`ReviewVerdict`.
    """
    raw = text or ""
    body = raw.strip()
    severity: VerdictSeverity = "ok"
    verdict_label = "green"

    for line in reversed(body.splitlines()):
        stripped = line.strip().lower()
        if stripped.startswith("## verdict:") or stripped.startswith("verdict:"):
            for marker in _VERDICT_TO_SEVERITY:
                if marker in stripped:
                    severity = _VERDICT_TO_SEVERITY[marker]
                    verdict_label = marker
                    break
            break
    else:
        lower = body.lower()
        if "red flag" in lower or "critical" in lower:
            severity = "critical"
            verdict_label = "red"
        elif "concern" in lower or "warning" in lower or "warn" in lower:
            severity = "warn"
            verdict_label = "yellow"

    endorsement_type: str | None
    if verdict_label == "green":
        endorsement_type = "verified-by-steward"
    elif verdict_label == "red":
        endorsement_type = "under-review"
    else:
        endorsement_type = "under-review"

    return ReviewVerdict(
        severity=severity,
        endorsement_type=endorsement_type,
        comment_md=body,
        raw_response=raw,
    )
