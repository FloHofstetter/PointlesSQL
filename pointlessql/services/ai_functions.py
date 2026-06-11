"""LLM completion runner backing the ``ai_*`` SQL functions.

The PQL engine registers DuckDB scalar functions (``ai_query``,
``ai_classify``, ``ai_extract``, ``ai_translate``, ``ai_mask``) on the
per-query connection whenever a governed SELECT references one.  Those
UDFs execute synchronously inside the engine's worker thread, so this
module speaks to the providers through their *sync* SDK clients rather
than the async Lens adapters.

Credential resolution mirrors Genie's: the workspace's first enabled
BYO Lens provider credential wins; when none exists, the ambient
``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` environment variables act
as the local-dev fallback.  The workspace is taken from the
``POINTLESSQL_WORKSPACE_ID`` env var so the same code path works in
the web process, the scheduler, and the notebook kernel subprocess.

Cost control is per query: each :class:`AiFunctionRunner` instance
lives for exactly one ``run_sql`` call, deduplicates repeated argument
tuples through an in-memory cache, and refuses to exceed
``max_calls_per_query`` distinct provider round-trips.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from pointlessql.config import Settings, get_settings
from pointlessql.exceptions import SQLExecutionError

logger = logging.getLogger(__name__)

# (system prompt, user template) per operation.  The templates keep
# answers terse and machine-consumable — these values land in result
# cells, not a chat transcript.
_PROMPTS: dict[str, tuple[str, str]] = {
    "query": (
        "You are a data assistant embedded in a SQL engine. Answer the "
        "instruction concisely. Return only the answer text with no "
        "preamble and no markdown.",
        "{0}",
    ),
    "classify": (
        "Classify the text into exactly one of the given labels. "
        "Respond with only the chosen label, verbatim.",
        "Labels: {1}\nText: {0}",
    ),
    "extract": (
        "Extract the requested field from the text. Respond with only "
        "the extracted value; respond with an empty string when the "
        "field is absent.",
        "Field: {1}\nText: {0}",
    ),
    "translate": (
        "Translate the text into the requested language. Respond with only the translation.",
        "Language: {1}\nText: {0}",
    ),
}

Completer = Callable[[str, str], str]
"""Signature of the provider seam: ``(system, user) -> completion``."""


def _resolve_completer(settings: Settings) -> Completer:
    """Build a sync completion callable from workspace creds or env keys.

    Propagates :class:`SQLExecutionError` from
    :func:`_resolve_provider` when no credential is available.

    Args:
        settings: Resolved application settings (model defaults,
            timeout, optional model override).

    Returns:
        A callable performing one provider round-trip.
    """
    provider, api_key, model = _resolve_provider(settings)
    timeout = settings.ai_functions.timeout_seconds
    max_tokens = max(64, settings.ai_functions.max_output_chars // 2)

    if provider == "anthropic":

        def _complete_anthropic(system: str, user: str) -> str:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = [block.text for block in response.content if block.type == "text"]
            return "".join(parts)

        return _complete_anthropic

    def _complete_openai(system: str, user: str) -> str:
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    return _complete_openai


def _resolve_provider(settings: Settings) -> tuple[str, str, str]:
    """Pick ``(provider, api_key, model)`` for the active workspace.

    Workspace-scoped Lens provider credentials win (same rows Genie
    consumes); ambient env keys are the fallback so local development
    works without the admin credential flow.

    Args:
        settings: Resolved application settings.

    Returns:
        The provider name (``anthropic`` / ``openai``), its API key,
        and the model to use.

    Raises:
        SQLExecutionError: When neither a workspace credential nor an
            env key is configured.
    """
    workspace_id = _workspace_id_from_env()
    override = settings.ai_functions.model

    try:
        from pointlessql.db import get_session_factory
        from pointlessql.services.lens._provider_creds import (
            decrypt_provider_key,
            list_provider_creds,
        )

        factory = get_session_factory()
        for row in list_provider_creds(factory, workspace_id=workspace_id):
            if not row.enabled:
                continue
            api_key = decrypt_provider_key(
                factory, workspace_id=workspace_id, provider=row.provider
            )
            if api_key is None:
                continue
            default_model = (
                settings.lens.openai_model_default
                if row.provider == "openai"
                else settings.lens.anthropic_model_default
            )
            return row.provider, api_key, override or row.default_model or default_model
    except Exception:  # noqa: BLE001 — fall through to env keys
        logger.debug("workspace LLM credential lookup failed", exc_info=True)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        return (
            "anthropic",
            anthropic_key,
            override or settings.lens.anthropic_model_default,
        )
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        return "openai", openai_key, override or settings.lens.openai_model_default

    raise SQLExecutionError(
        "AI functions need a configured LLM provider — add a Lens "
        "provider credential in the admin UI or set ANTHROPIC_API_KEY / "
        "OPENAI_API_KEY."
    )


def _workspace_id_from_env() -> int:
    """Return the ambient workspace id (kernel/scheduler env), default 1."""
    raw = os.environ.get("POINTLESSQL_WORKSPACE_ID", "").strip()
    try:
        return int(raw) if raw else 1
    except ValueError:
        return 1


class AiFunctionRunner:
    """Per-query executor behind the registered ``ai_*`` UDFs.

    One instance serves exactly one SQL execution: the dedup cache and
    the call counter therefore bound the *query's* provider spend, not
    the process's.  The provider completer resolves lazily on the
    first LLM-backed call so a query that only uses the deterministic
    ``ai_mask`` never touches credentials.

    Args:
        settings: Application settings; resolved via
            :func:`get_settings` when omitted.
        completer: Optional pre-resolved provider seam (tests inject
            a fake here; production resolves lazily).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        completer: Completer | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._completer = completer
        self._cache: dict[tuple[str, ...], str] = {}
        self.calls = 0

    def run(self, op: str, *args: str | None) -> str | None:
        """Execute one ``ai_*`` operation for one row.

        Args:
            op: Operation key (``query`` / ``classify`` / ``extract``
                / ``translate``).
            *args: Positional string arguments from the SQL call.

        Returns:
            The completion text (possibly cached), or ``None`` when
            the first argument is NULL.

        Raises:
            SQLExecutionError: When the per-query call cap is reached
                or no provider is configured.
        """
        if not args or args[0] is None:
            return None
        key = (op, *[a if a is not None else "" for a in args])
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        max_calls = self._settings.ai_functions.max_calls_per_query
        if self.calls >= max_calls:
            raise SQLExecutionError(
                f"ai_{op}: query exceeded the {max_calls}-call AI-function "
                "budget (POINTLESSQL_AI_FUNCTIONS_MAX_CALLS_PER_QUERY). "
                "Reduce the row count (e.g. LIMIT / pre-aggregate) or "
                "raise the budget."
            )
        if self._completer is None:
            self._completer = _resolve_completer(self._settings)

        system, template = _PROMPTS[op]
        user = template.format(*[a if a is not None else "" for a in args])
        self.calls += 1
        try:
            text = self._completer(system, user)
        except SQLExecutionError:
            raise
        except Exception as exc:
            raise SQLExecutionError(f"ai_{op}: provider call failed: {exc}") from exc
        text = (text or "").strip()[: self._settings.ai_functions.max_output_chars]
        self._cache[key] = text
        return text

    def mask(self, value: str | None) -> str | None:
        """Deterministically mask *value* (no LLM round-trip).

        Args:
            value: The raw cell text; ``None`` passes through.

        Returns:
            The masked text from the shared PII masking helper.
        """
        if value is None:
            return None
        from pointlessql.services.pii import mask_value

        return mask_value(value)


def build_runner(settings: Settings | None = None) -> AiFunctionRunner:
    """Construct the per-query runner (seam for the PQL engine + tests).

    Args:
        settings: Optional settings override.

    Returns:
        A fresh :class:`AiFunctionRunner`.
    """
    return AiFunctionRunner(settings)
