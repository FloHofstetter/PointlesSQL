"""Cedar engine wrapper with fail-closed semantics.

The engine takes a list of authored ``PolicyModule`` rows, assembles
their ``cedar_source`` into one Cedar policy set, and evaluates a
single request through ``cedarpy.is_authorized``.

Fail-closed semantics — three failure modes all collapse to ``deny``:

1. **Empty policy set** — no modules linked.  The caller decides
   whether absence-of-policy means *allow* (open by default) or
   *deny* (closed by default); the engine surfaces the empty-set
   case via ``Decision.empty`` so the caller can pick.
2. **Parse error** in any module — Cedar raises during compilation;
   we trap, mark every linked module as having errored, and return
   ``Decision.forbid``.  The audit trail carries the error message.
3. **Runtime error** in evaluation — Cedar raises during
   ``is_authorized``; same fail-closed treatment, same audit
   surfacing.

The parsed policy set is cached on ``(module_id, version)`` tuples
so a 1k-eval / sec hot path avoids re-parsing.  Cache is process-
local; restart clears it.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from typing import Any

import cedarpy

from pointlessql.models import PolicyModule

logger = logging.getLogger(__name__)

#: Default-deny reason persisted in the audit trail when the
#: engine fails closed due to parse / runtime errors.
CEDAR_DEFAULT_DENY_REASON: str = "cedar_fail_closed"


@dataclasses.dataclass(slots=True, frozen=True)
class Decision:
    """Outcome of one ``cedar_evaluate`` call.

    Attributes:
        effect: ``permit`` or ``forbid``.  Empty / errored policy sets
            collapse to ``forbid`` for fail-closed semantics.
        empty: True when no policy modules were supplied; the caller
            decides whether to treat the empty case as open or closed.
        latency_ms: Engine latency in milliseconds; ``None`` when the
            parse step never completed.
        diagnostics: Cedar diagnostic reasons (matched policy ids,
            error messages); shape is engine-defined.
        error_class: ``cedar_parse_error`` / ``cedar_runtime_error`` /
            ``None`` when evaluation succeeded.
    """

    effect: str
    empty: bool
    latency_ms: int | None
    diagnostics: dict[str, Any]
    error_class: str | None = None


_cache: dict[tuple[int, int], str] = {}
_cache_lock = threading.Lock()


def invalidate_cache(module_id: int | None = None) -> None:
    """Drop the parsed-policy cache.

    Args:
        module_id: When given, drop only entries for that module id;
            otherwise drop everything.  Module-scoped invalidation is
            used by CRUD on edit so other workspaces' caches survive.
    """
    with _cache_lock:
        if module_id is None:
            _cache.clear()
            return
        for key in [k for k in _cache if k[0] == module_id]:
            _cache.pop(key, None)


def _compose_policies(modules: list[PolicyModule]) -> str:
    """Return the concatenated Cedar source of *modules*, cached.

    The cache key is the tuple of ``(module_id, version)`` pairs in
    the input order so any edit-bump invalidates automatically.
    """
    with _cache_lock:
        for module in modules:
            key = (int(module.id), int(module.version))
            if key not in _cache:
                _cache[key] = str(module.cedar_source or "").strip()
        return "\n\n".join(_cache[(int(m.id), int(m.version))] for m in modules)


def cedar_evaluate(
    modules: list[PolicyModule],
    *,
    principal: str,
    action: str,
    resource: str,
    context: dict[str, Any] | None = None,
    entities: list[dict[str, Any]] | None = None,
) -> Decision:
    """Evaluate one Cedar request against *modules*.

    Args:
        modules: Active, enabled :class:`PolicyModule` rows in the
            order they should be composed.  Pass ``[]`` to signal
            "no policies configured" — returns ``Decision.empty`` so
            the caller can decide whether to open or close.
        principal: Cedar principal UID (``User::"alice"``).
        action: Cedar action UID (``Action::"read"``).
        resource: Cedar resource UID (``DataProduct::"main.silver"``).
        context: Optional context dict (request attributes).
        entities: Optional entity payload list (Cedar JSON format).

    Returns:
        A :class:`Decision` carrying the effect, latency, diagnostics,
        and error class on failure.  Fail-closed on every error path.
    """
    if not modules:
        return Decision(
            effect="forbid",
            empty=True,
            latency_ms=0,
            diagnostics={"reason": "empty_policy_set"},
        )
    try:
        composed = _compose_policies(modules)
    except (ValueError, TypeError) as exc:  # noqa: BLE001
        # bare-broad-ok: cache-compose only catches str-cast errors.
        # A broken policy module denying access is a config failure the
        # operator must see — the audit row alone is invisible in the log
        # stream.
        logger.warning(
            "Cedar policy compose failed; failing closed (forbid)",
            exc_info=True,
            extra={
                "error_class": "cedar_parse_error",
                "cedar_action": action,
                "cedar_resource": resource,
            },
        )
        return Decision(
            effect="forbid",
            empty=False,
            latency_ms=None,
            diagnostics={"reason": "compose_failed", "message": str(exc)},
            error_class="cedar_parse_error",
        )
    request = {
        "principal": principal,
        "action": action,
        "resource": resource,
        "context": context or {},
    }
    start = time.monotonic()
    try:
        result = cedarpy.is_authorized(
            request=request,
            policies=composed,
            entities=entities or [],
        )
    # bare-broad-ok: Cedar raises arbitrary classes; collapse to fail-closed.
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "Cedar evaluation raised; failing closed (forbid)",
            exc_info=True,
            extra={
                "error_class": "cedar_runtime_error",
                "cedar_action": action,
                "cedar_resource": resource,
            },
        )
        return Decision(
            effect="forbid",
            empty=False,
            latency_ms=latency_ms,
            diagnostics={"message": str(exc)},
            error_class="cedar_runtime_error",
        )
    latency_ms = int((time.monotonic() - start) * 1000)
    allowed = bool(getattr(result, "allowed", False))
    diagnostics = _serialise_diagnostics(result)
    decision_label = str(diagnostics.get("decision", ""))
    error_class: str | None = None
    if diagnostics.get("errors"):
        error_class = "cedar_parse_error"
    elif "NoDecision" in decision_label and not allowed:
        error_class = "cedar_runtime_error"
    if error_class is not None:
        # Cedar returned (without raising) a decision carrying errors or no
        # decision — still a fail-closed outcome the operator should see.
        logger.warning(
            "Cedar returned a fail-closed decision with errors; forbidding",
            extra={
                "error_class": error_class,
                "cedar_action": action,
                "cedar_resource": resource,
            },
        )
    return Decision(
        effect="permit" if allowed else "forbid",
        empty=False,
        latency_ms=latency_ms,
        diagnostics=diagnostics,
        error_class=error_class,
    )


def _serialise_diagnostics(result: Any) -> dict[str, Any]:
    """Best-effort serialisation of Cedar's Diagnostics object."""
    diag = getattr(result, "diagnostics", None)
    if diag is None:
        return {}
    reasons = list(getattr(diag, "reasons", []) or [])
    errors = list(getattr(diag, "errors", []) or [])
    decision = str(getattr(result, "decision", ""))
    return {
        "decision": decision,
        "reasons": [str(r) for r in reasons],
        "errors": [str(e) for e in errors],
    }
