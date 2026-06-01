"""Unit tests for the inline AWS Signature Version 4 signer.

The signer is deterministic given a fixed ``now``, so correctness is
checked two ways: against external known-answers (the SHA-256 of the
empty body, the canonical credential-scope shape) and against an
independent re-derivation of the signature that follows the published
SigV4 algorithm. The independent derivation is a genuine cross-check —
a regression in the canonical-request layout or the key-derivation
order would have to break both implementations identically to pass.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac

import pytest

from pointlessql.services.aws_sigv4 import sign_request

# SHA-256 of the empty byte string — a fixed external known-answer.
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

_FIXED_NOW = datetime.datetime(2015, 8, 30, 12, 36, 0, tzinfo=datetime.UTC)

_COMMON = {
    "method": "PUT",
    "url": "https://example-bucket.s3.eu-central-1.amazonaws.com/path/to/key",
    "region": "eu-central-1",
    "service": "s3",
    "access_key_id": "AKIDEXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
}


def _independent_signature(
    *,
    method: str,
    host: str,
    canonical_uri: str,
    canonical_qs: str,
    region: str,
    service: str,
    secret: str,
    amz_date: str,
    date_stamp: str,
    payload_hash: str,
    extra: dict[str, str],
) -> str:
    """Re-derive the SigV4 signature straight from the spec, independently."""
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    for k, v in extra.items():
        headers[k.lower()] = v
    names = sorted(headers)
    canonical_headers = "".join(f"{k}:{headers[k].strip()}\n" for k in names)
    signed_headers = ";".join(names)
    canonical_request = (
        f"{method}\n{canonical_uri}\n{canonical_qs}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    sts = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n{scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hmac(b"AWS4" + secret.encode(), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    return hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()


def test_matches_independent_derivation() -> None:
    headers = sign_request(
        **_COMMON,
        body=b"hello world",
        extra_headers={"Content-Type": "application/octet-stream"},
        now=_FIXED_NOW,
    )
    expected_sig = _independent_signature(
        method="PUT",
        host="example-bucket.s3.eu-central-1.amazonaws.com",
        canonical_uri="/path/to/key",
        canonical_qs="",
        region="eu-central-1",
        service="s3",
        secret=_COMMON["secret_access_key"],
        amz_date="20150830T123600Z",
        date_stamp="20150830",
        payload_hash=hashlib.sha256(b"hello world").hexdigest(),
        extra={"Content-Type": "application/octet-stream"},
    )
    assert f"Signature={expected_sig}" in headers["Authorization"]


def test_empty_body_payload_hash_is_known_answer() -> None:
    headers = sign_request(**_COMMON, now=_FIXED_NOW)
    assert headers["x-amz-content-sha256"] == _EMPTY_SHA256


def test_authorization_shape() -> None:
    headers = sign_request(**_COMMON, now=_FIXED_NOW)
    auth = headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 ")
    assert "Credential=AKIDEXAMPLE/20150830/eu-central-1/s3/aws4_request" in auth
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in auth
    sig = auth.split("Signature=", 1)[1]
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_amz_date_and_host_from_inputs() -> None:
    headers = sign_request(**_COMMON, now=_FIXED_NOW)
    assert headers["x-amz-date"] == "20150830T123600Z"
    assert headers["Host"] == "example-bucket.s3.eu-central-1.amazonaws.com"


def test_deterministic_for_fixed_now() -> None:
    a = sign_request(**_COMMON, body=b"x", now=_FIXED_NOW)
    b = sign_request(**_COMMON, body=b"x", now=_FIXED_NOW)
    assert a == b


def test_body_change_changes_signature() -> None:
    a = sign_request(**_COMMON, body=b"one", now=_FIXED_NOW)
    b = sign_request(**_COMMON, body=b"two", now=_FIXED_NOW)
    assert a["Authorization"] != b["Authorization"]


def test_region_change_changes_signature() -> None:
    base = dict(_COMMON)
    a = sign_request(**base, now=_FIXED_NOW)
    base["region"] = "us-east-1"
    b = sign_request(**base, now=_FIXED_NOW)
    assert a["Authorization"] != b["Authorization"]


def test_extra_headers_are_signed_and_returned_verbatim() -> None:
    headers = sign_request(
        **_COMMON,
        extra_headers={"Content-Type": "text/plain"},
        now=_FIXED_NOW,
    )
    # Returned with original casing...
    assert headers["Content-Type"] == "text/plain"
    # ...and folded (lowercased) into the signed-headers list.
    assert "content-type;host" in headers["Authorization"]


def test_microseconds_are_stripped() -> None:
    now = datetime.datetime(2015, 8, 30, 12, 36, 0, 999, tzinfo=datetime.UTC)
    headers = sign_request(**_COMMON, now=now)
    assert headers["x-amz-date"] == "20150830T123600Z"


@pytest.mark.parametrize(
    ("url_path", "expected_uri"),
    [
        ("https://h.example.com", "/"),
        ("https://h.example.com/a/b", "/a/b"),
        ("https://h.example.com/with space", "/with%20space"),
    ],
)
def test_canonical_uri_via_signature_stability(url_path: str, expected_uri: str) -> None:
    # Two calls with the same path agree; a path with a space is encoded
    # (asserted indirectly: signing succeeds and host parsing is correct).
    headers = sign_request(
        method="GET",
        url=url_path,
        region="eu-central-1",
        service="s3",
        access_key_id="AKIDEXAMPLE",
        secret_access_key="secret",
        now=_FIXED_NOW,
    )
    assert headers["Host"] == "h.example.com"
    expected_sig = _independent_signature(
        method="GET",
        host="h.example.com",
        canonical_uri=expected_uri,
        canonical_qs="",
        region="eu-central-1",
        service="s3",
        secret="secret",
        amz_date="20150830T123600Z",
        date_stamp="20150830",
        payload_hash=_EMPTY_SHA256,
        extra={},
    )
    assert f"Signature={expected_sig}" in headers["Authorization"]
