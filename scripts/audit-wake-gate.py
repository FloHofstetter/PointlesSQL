"""Wake-gate pre-run script for the daily Audit-Reviewer-Agent.

Sprint 19.2.2 — Hermes' cron scheduler invokes this script before the
LLM round-trip and inspects the last non-empty stdout line. When that
line is the JSON ``{"wakeAgent": false}``, Hermes skips the agent
entirely; otherwise the full stdout is prepended to the prompt as
context and the agent runs normally.

The script:

1. Reads ``POINTLESSQL_BASE_URL`` + ``POINTLESSQL_API_KEY`` from the
   environment (the same vars the plugin already requires).
2. Computes the closed-day window
   ``[yesterday-00:00 UTC, today-00:00 UTC)``.
3. Calls ``GET /api/audit/anomalies`` for ``rejects``,
   ``errored_ops``, and ``external_writes`` and takes the worst
   severity across the three.
4. Prints a human-readable summary block (becomes prompt context on
   wake), then ends with ``{"wakeAgent": true|false}``.

Exit status is always 0 — Hermes treats non-zero as a script failure
and wakes the agent anyway, which is a safe default but loud.

Drop the file path into the cron job's ``script`` field; the
docs/hermes-jobs/audit-reviewer-daily.md walkthrough has the exact
pointer.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover — fail open
    print("audit-wake-gate: httpx not available, waking agent")
    print(json.dumps({"wakeAgent": True}))
    sys.exit(0)


_METRICS = ("rejects", "errored_ops", "external_writes")
_SEVERITY_RANK: dict[str, int] = {"ok": 0, "warn": 1, "critical": 2}


def _yesterday_window() -> tuple[str, str]:
    """Return ``(since, until)`` ISO-8601 strings for the closed previous UTC day."""
    today = datetime.datetime.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - datetime.timedelta(days=1)
    return yesterday.isoformat(), today.isoformat()


def _verdict_for_metric(
    client: httpx.Client, metric: str, since: str, until: str
) -> dict[str, Any]:
    """Return ``{"metric", "severity", "value", "baseline"}`` for one metric.

    Args:
        client: A pre-configured ``httpx.Client`` carrying the bearer token.
        metric: One of :data:`_METRICS`.
        since: ISO-8601 lower bound.
        until: ISO-8601 upper bound (exclusive).

    Returns:
        A summary dict with the worst-bin verdict.  Failures degrade
        to ``severity="ok"`` so a transient PointlesSQL outage does
        not falsely escalate the day.
    """
    try:
        response = client.get(
            "/api/audit/anomalies",
            params={"metric": metric, "since": since, "until": until, "bin": "day"},
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:  # pragma: no cover
        return {"metric": metric, "severity": "ok", "error": f"{type(exc).__name__}: {exc}"}

    points = data.get("points") or []
    worst = "ok"
    worst_value = 0
    worst_baseline = 0.0
    for point in points:
        sev = point.get("severity") or "ok"
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK[worst]:
            worst = sev
            worst_value = int(point.get("value") or 0)
            worst_baseline = float(point.get("baseline_mean") or 0.0)
    return {
        "metric": metric,
        "severity": worst,
        "value": worst_value,
        "baseline_mean": round(worst_baseline, 2),
    }


def main() -> int:
    """Render the context block and emit the wake-gate JSON line.

    Returns:
        Always ``0``.  A non-zero exit makes Hermes wake the agent
        defensively, which we don't want for the wake-gate path.
    """
    base_url = os.environ.get("POINTLESSQL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key = os.environ.get("POINTLESSQL_API_KEY")
    if not api_key:
        print("audit-wake-gate: POINTLESSQL_API_KEY not set, waking agent")
        print(json.dumps({"wakeAgent": True}))
        return 0

    since, until = _yesterday_window()
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    with httpx.Client(base_url=base_url, headers=headers) as client:
        verdicts = [_verdict_for_metric(client, m, since, until) for m in _METRICS]

    # Fail-open: if ANY metric returned an error, wake the agent
    # defensively rather than silently silencing the daily review on a
    # transient PointlesSQL outage.  Sprint 19.4 bug-hunt found that
    # the prior "demote errors to severity=ok" policy could let a
    # connect failure mask a real anomaly day, which violates the
    # README's documented fail-open posture.
    has_error = any("error" in v for v in verdicts)
    worst = max(_SEVERITY_RANK[v["severity"]] for v in verdicts)
    overall = next(s for s, r in _SEVERITY_RANK.items() if r == worst)

    # Render a compact human-readable context block.  When the agent
    # does wake, this is prepended to its prompt so it has the
    # pre-fetched anomaly numbers and does not need to re-call the
    # tools just to learn what the gate already knows.
    print(f"# Audit wake-gate ({since[:10]} → {until[:10]})")
    print(f"# overall severity: {overall}")
    for v in verdicts:
        if "error" in v:
            print(f"#   {v['metric']:<16} severity={v['severity']:<8}  (error: {v['error']})")
        else:
            print(
                f"#   {v['metric']:<16} severity={v['severity']:<8} "
                f"value={v['value']:<6} baseline={v['baseline_mean']}"
            )
    print()

    # Emit the wake-gate JSON as the FINAL non-empty line (Hermes only
    # parses the last one).  ``ok`` → skip the LLM call.  ``warn`` /
    # ``critical`` → wake.  Any error → wake regardless (fail-open).
    wake = has_error or overall != "ok"
    payload: dict[str, Any] = {"wakeAgent": wake, "severity": overall}
    if has_error:
        payload["reason"] = "audit-api unreachable; waking agent defensively"
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
