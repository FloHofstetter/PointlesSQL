"""Egress guard against server-side request forgery (SSRF).

Several features contact a destination URL that an end user supplies —
alert webhooks, marketplace notification subscriptions, review
forwards.  Without a host check a user can point one at the cloud
metadata endpoint (``169.254.169.254``), ``localhost``, or an internal
service and turn PointlesSQL into an SSRF proxy that exfiltrates
credentials or reaches the private network.

:func:`assert_public_http_url` resolves the host and refuses any
address that is loopback, private, link-local, reserved, multicast, or
unspecified (IPv4-mapped IPv6 is unwrapped first, so
``::ffff:169.254.169.254`` is caught too).  Call it both when a URL is
persisted *and* again immediately before the request fires, so a DNS
rebind between those two moments is still rejected.

The guard is governed by :class:`pointlessql.config.EgressSettings`:
``enabled`` (default on) flips the whole check, ``allow_private`` is the
explicit escape hatch for installs that deliberately target an internal
relay, and ``allowed_hosts`` is an optional hostname allowlist that
further narrows what may be reached.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from pointlessql.config import get_settings


class EgressError(ValueError):
    """Raised when a destination URL is not allowed to be contacted.

    A :class:`ValueError` subclass so callers that already funnel bad
    input into a 400/validation path catch it without importing this
    module's type.
    """


def _parse_allowed_hosts(raw: str) -> frozenset[str]:
    """Return the lower-cased hostname allowlist parsed from *raw*.

    Args:
        raw: Comma-separated hostnames from ``EgressSettings.allowed_hosts``.

    Returns:
        A frozenset of trimmed, lower-cased hostnames; empty when *raw*
        is blank (meaning "any public host is allowed").
    """
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _host_is_blocked_ip_literal(host: str) -> bool:
    """Return whether *host* is an IP literal that resolves to a blocked address.

    Used for schemes that do not go through DNS resolution (e.g. an
    ``s3://`` bucket host), where the only internal-target risk is a raw
    IP written directly into the URL.

    Args:
        host: The hostname component of a URL.

    Returns:
        ``True`` when *host* parses as an IP address that
        :func:`_is_blocked_ip` rejects; ``False`` for ordinary names.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return _is_blocked_ip(ip)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether *ip* is a non-public address the guard must reject.

    Args:
        ip: A parsed address (IPv4-mapped IPv6 is unwrapped first).

    Returns:
        ``True`` for loopback / private / link-local / reserved /
        multicast / unspecified addresses.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_http_url(url: str) -> None:
    """Raise :class:`EgressError` unless *url* targets a public http(s) host.

    No-ops when ``EgressSettings.enabled`` is false.  Otherwise the URL
    must use the ``http``/``https`` scheme, pass the optional
    ``allowed_hosts`` allowlist, and resolve exclusively to public
    addresses (unless ``allow_private`` is set).

    Args:
        url: The destination URL to validate.

    Raises:
        EgressError: When the scheme is not http(s), the host is empty,
            outside the allowlist, unresolvable, or resolves to any
            non-public address.
    """
    egress = get_settings().egress
    if not egress.enabled:
        return

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise EgressError(f"egress blocked: scheme {parts.scheme!r} is not http or https")
    host = parts.hostname
    if not host:
        raise EgressError("egress blocked: URL has no host")

    allowed = _parse_allowed_hosts(egress.allowed_hosts)
    if allowed and host.lower() not in allowed:
        raise EgressError(f"egress blocked: host {host!r} is not in the egress allowlist")

    if egress.allow_private:
        return

    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise EgressError(f"egress blocked: cannot resolve host {host!r}") from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise EgressError(f"egress blocked: unparseable address {address!r}") from exc
        if _is_blocked_ip(ip):
            raise EgressError(
                f"egress blocked: host {host!r} resolves to non-public address {address}"
            )


def assert_public_s3_url(url: str) -> None:
    """Raise :class:`EgressError` unless *url* is an ``s3://`` URL with a safe host.

    DuckDB's S3 reader targets the AWS endpoint for the bucket, so the
    bucket name — not a network host — fills the URL host slot.  The only
    direct internal-target risk is a raw IP or ``localhost`` written as
    the bucket host, which this rejects.  No-ops when the guard is
    disabled.

    Args:
        url: The ``s3://bucket/key`` URL to validate.

    Raises:
        EgressError: When the scheme is not ``s3`` or the bucket host is
            ``localhost`` / a raw internal IP literal.
    """
    egress = get_settings().egress
    if not egress.enabled:
        return
    parts = urlsplit(url)
    if parts.scheme != "s3":
        raise EgressError(f"egress blocked: expected an s3:// URL, got scheme {parts.scheme!r}")
    host = (parts.hostname or "").lower()
    if not host:
        raise EgressError("egress blocked: s3 URL has no bucket host")
    if egress.allow_private:
        return
    if host == "localhost" or _host_is_blocked_ip_literal(host):
        raise EgressError(f"egress blocked: s3 bucket host {host!r} is a raw internal address")
