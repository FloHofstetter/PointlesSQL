"""Tests for the Kimi (Moonshot) and Grok (xAI) Lens provider adapters.

The adapters reuse the OpenAI-compatible wire format, so the unit tests
assert the dispatch / base-url / pricing wiring without a live API; one
route test drives the session-create endpoint end-to-end to prove the
``LENS_PROVIDERS`` bump and the per-provider model-default resolution.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.config import get_settings
from pointlessql.models import LENS_PROVIDERS
from pointlessql.services.lens.llm_provider import (
    GrokProvider,
    KimiProvider,
    OpenAIProvider,
    _estimate_cost_usd,
    get_provider,
)


def test_lens_providers_includes_kimi_and_grok() -> None:
    assert "kimi" in LENS_PROVIDERS
    assert "grok" in LENS_PROVIDERS
    # Pre-existing providers stay registered.
    assert "openai" in LENS_PROVIDERS
    assert "anthropic" in LENS_PROVIDERS


def test_get_provider_dispatches_kimi_and_grok() -> None:
    kimi = get_provider("kimi", api_key="sk-test")
    assert isinstance(kimi, KimiProvider)
    assert kimi.name == "kimi"
    assert kimi.base_url == "https://api.moonshot.ai/v1"

    grok = get_provider("grok", api_key="sk-test")
    assert isinstance(grok, GrokProvider)
    assert grok.name == "grok"
    assert grok.base_url == "https://api.x.ai/v1"


def test_kimi_grok_subclass_openai_adapter() -> None:
    # They inherit the OpenAI chat.completions translation.
    assert issubclass(KimiProvider, OpenAIProvider)
    assert issubclass(GrokProvider, OpenAIProvider)
    # The base adapter still targets OpenAI itself.
    assert OpenAIProvider(api_key="sk-test").base_url is None


def test_get_provider_still_handles_known_and_unknown() -> None:
    assert get_provider("openai", api_key="k").name == "openai"
    assert get_provider("anthropic", api_key="k").name == "anthropic"
    with pytest.raises(ValueError, match="Unrecognised Lens provider"):
        get_provider("bogus", api_key="k")


def test_pricing_tables_cover_kimi_and_grok() -> None:
    kimi_cost = _estimate_cost_usd(
        provider="kimi", model="kimi-k2-0711-preview", tokens_in=1_000_000, tokens_out=0
    )
    assert kimi_cost == pytest.approx(0.60)
    grok_cost = _estimate_cost_usd(
        provider="grok", model="grok-4", tokens_in=0, tokens_out=1_000_000
    )
    assert grok_cost == pytest.approx(15.00)
    # Unknown model under a known provider uses the conservative fallback.
    fallback = _estimate_cost_usd(
        provider="kimi", model="nonexistent", tokens_in=1_000_000, tokens_out=0
    )
    assert fallback == pytest.approx(5.00)


def test_settings_model_default_per_provider() -> None:
    lens = get_settings().lens
    assert lens.model_default("kimi") == lens.kimi_model_default
    assert lens.model_default("grok") == lens.grok_model_default
    assert lens.model_default("openai") == lens.openai_model_default
    assert lens.model_default("anthropic") == lens.anthropic_model_default
    # Unknown provider falls back to the OpenAI default rather than Anthropic.
    assert lens.model_default("bogus") == lens.openai_model_default


@pytest.mark.asyncio
async def test_create_session_accepts_kimi_provider(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "kimi session", "llm_provider": "kimi"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["llm_provider"] == "kimi"
    # Default model resolves to the Kimi default, not the Anthropic one.
    assert payload["llm_model"] == get_settings().lens.kimi_model_default
