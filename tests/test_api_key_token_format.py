"""Tests for the Phase 118 v1 token format module."""

from __future__ import annotations

import re

import pytest

from pointlessql.services.api_keys._token_format import (
    V1_REGEX,
    _crc8_for,
    display_prefix_for,
    generate_v1_token,
    parse_v1_token,
)


def test_v1_regex_matches_generated_live_token() -> None:
    pattern = re.compile(f"^{V1_REGEX}$")
    for _ in range(50):
        token = generate_v1_token("live")
        assert pattern.match(token), f"regex mismatch for {token!r}"


def test_v1_regex_matches_generated_test_token() -> None:
    pattern = re.compile(f"^{V1_REGEX}$")
    for _ in range(50):
        token = generate_v1_token("test")
        assert pattern.match(token), f"regex mismatch for {token!r}"


def test_generate_rejects_unknown_env() -> None:
    with pytest.raises(ValueError, match=r"env must be one of"):
        generate_v1_token("prod")  # type: ignore[arg-type]


def test_generated_token_total_length_is_61() -> None:
    # pql_(4) + _(1) + live/test(4) + _(1) + v1(2) + _(1) + body(40) + _(1) + crc(8)
    token = generate_v1_token("live")
    assert len(token) == 3 + 1 + 4 + 1 + 2 + 1 + 40 + 1 + 8


def test_crc_is_deterministic_for_fixed_input() -> None:
    body = "pql_live_v1_" + "a" * 40
    assert _crc8_for(body) == _crc8_for(body)
    # And a different input yields a different CRC.
    other = "pql_test_v1_" + "a" * 40
    assert _crc8_for(body) != _crc8_for(other)


def test_parse_roundtrip_recovers_env_and_body() -> None:
    for env in ("live", "test"):
        token = generate_v1_token(env)  # type: ignore[arg-type]
        parsed = parse_v1_token(token)
        assert parsed is not None
        recovered_env, body, crc = parsed
        assert recovered_env == env
        assert len(body) == 40
        assert all(c.isalnum() for c in body)
        assert len(crc) == 8
        # Rebuilding from parts must yield the original token.
        assert f"pql_{recovered_env}_v1_{body}_{crc}" == token


def test_parse_returns_none_for_legacy_secrets_token_urlsafe() -> None:
    # secrets.token_urlsafe(32) yields ~43-char base64-url; no pql_ prefix.
    legacy = "kMqz4_AB-CdEfGhIjKlMnOpQrStUvWxYz0123456789x"
    assert parse_v1_token(legacy) is None


def test_parse_returns_none_for_wrong_crc() -> None:
    token = generate_v1_token("live")
    # Flip the last hex digit to break the CRC.
    last = token[-1]
    swapped = "0" if last != "0" else "1"
    tampered = token[:-1] + swapped
    assert parse_v1_token(tampered) is None


def test_parse_returns_none_for_empty_or_none() -> None:
    assert parse_v1_token("") is None
    assert parse_v1_token("   ") is None  # whitespace doesn't match the regex


def test_parse_returns_none_for_unknown_version() -> None:
    # v2 isn't supported by parse_v1_token.
    token = "pql_live_v2_" + "a" * 40 + "_" + "a" * 8
    assert parse_v1_token(token) is None


def test_parse_returns_none_for_unknown_env() -> None:
    # Construct a syntactically v1-shaped token with env=prod.
    body = "a" * 40
    crc = _crc8_for(f"pql_prod_v1_{body}")
    token = f"pql_prod_v1_{body}_{crc}"
    assert parse_v1_token(token) is None


def test_display_prefix_for_v1_token_includes_env_and_first_body_chars() -> None:
    token = generate_v1_token("live")
    prefix = display_prefix_for(token)
    assert prefix.startswith("pql_live_v1_")
    assert len(prefix) == len("pql_live_v1_") + 10


def test_display_prefix_for_legacy_token_falls_back_to_first_8() -> None:
    legacy = "kMqz4_AB-CdEfGhIjKlMnOpQrStUvWxYz0123456789x"
    assert display_prefix_for(legacy) == legacy[:8]


def test_two_generated_tokens_are_distinct() -> None:
    tokens = {generate_v1_token("live") for _ in range(100)}
    assert len(tokens) == 100
