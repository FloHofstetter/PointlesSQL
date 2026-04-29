"""Minimal AWS Signature Version 4 signing for httpx requests.

A handful of audit-stream sinks (S3 PutObject, CloudTrail PutEvents)
need SigV4-signed HTTP requests.  Pulling boto3 in for ~50 lines of
signing logic would dominate the dependency footprint, so we sign
inline using the public AWS spec
(https://docs.aws.amazon.com/general/latest/gr/sigv4-signed-request-examples.html).

The function returns the signed headers dict; the caller passes
those to :class:`httpx.AsyncClient` along with the body.  Keep this
module narrowly scoped — extending it with full request-builder
ergonomics belongs in a dedicated AWS client, not here.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
from urllib.parse import quote


def _sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of *data*."""
    return hashlib.sha256(data).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256(key, msg) raw bytes — the SigV4 derivation step."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_signing_key(
    secret_access_key: str,
    date_stamp: str,
    region: str,
    service: str,
) -> bytes:
    """Derive the date/region/service/aws4_request signing key."""
    k_date = _sign(b"AWS4" + secret_access_key.encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _canonical_uri(path: str) -> str:
    """URL-encode *path* per SigV4 (S3 keeps slashes, CloudTrail collapses to ``/``)."""
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return quote(path, safe="/-_.~")


def sign_request(
    *,
    method: str,
    url: str,
    region: str,
    service: str,
    access_key_id: str,
    secret_access_key: str,
    body: bytes = b"",
    extra_headers: dict[str, str] | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, str]:
    """Return the SigV4 ``Authorization`` + ``x-amz-*`` headers for one request.

    Args:
        method: HTTP method, e.g. ``"PUT"`` or ``"POST"``.
        url: Full request URL.  The host comes from this; the path
            (and any query string) goes into the canonical request.
        region: AWS region, e.g. ``"eu-central-1"``.
        service: AWS service code, e.g. ``"s3"`` or ``"events"``.
            CloudTrail ingestion lives behind the ``cloudtrail-data``
            service per the PutAuditEvents API.
        access_key_id: IAM access key.
        secret_access_key: IAM secret access key.
        body: Raw request body bytes.  S3 PUT requires this to be
            included in the canonical request even when empty.
        extra_headers: Caller-set headers that participate in the
            signed-headers list.  ``Content-Type`` is the typical
            one; do not pre-add ``Authorization`` or ``x-amz-*``
            headers — this function fills those.
        now: Override for the request time, used only by tests.

    Returns:
        A dict of headers including ``Authorization``,
        ``x-amz-date``, ``x-amz-content-sha256`` and the
        ``Host`` header.  Pass the dict verbatim to httpx.
    """
    from urllib.parse import urlsplit

    extra = dict(extra_headers or {})
    parsed = urlsplit(url)
    host = parsed.netloc
    canonical_uri = _canonical_uri(parsed.path)
    canonical_qs = parsed.query  # SigV4 wants RFC3986-encoded; we accept simple keys here

    timestamp = (now or datetime.datetime.now(datetime.UTC)).replace(microsecond=0)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")

    payload_hash = _sha256_hex(body)

    signed_input_headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    for k, v in extra.items():
        signed_input_headers[k.lower()] = v

    signed_header_names = sorted(signed_input_headers.keys())
    canonical_headers = "".join(
        f"{k}:{signed_input_headers[k].strip()}\n" for k in signed_header_names
    )
    signed_headers = ";".join(signed_header_names)

    canonical_request = (
        f"{method.upper()}\n"
        f"{canonical_uri}\n"
        f"{canonical_qs}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{_sha256_hex(canonical_request.encode('utf-8'))}"
    )

    signing_key = _derive_signing_key(secret_access_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    out = {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Host": host,
    }
    out.update(extra)
    return out
