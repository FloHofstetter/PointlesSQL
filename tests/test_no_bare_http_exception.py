"""Sprint 43.3 lint-style guard against bare ``raise HTTPException`` regressions.

The 38-site bare-string sweep funnelled every domain failure through
:class:`pointlessql.exceptions.PointlessSQLError` so the centralised
RFC 9457 handler renders a domain-named ``code`` instead of the
fall-through ``http_NNN``.  Two residual sites that have no
domain-named home (proxy upstream errors → 502) keep the bare form
and carry a ``# bare-http-ok: <reason>`` allowlist comment on the
preceding line.

This test fails on any new ``raise HTTPException(...)`` site that
does not carry the allowlist marker, so the conversion stays sticky.
"""

from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent.parent / "pointlessql" / "api"
_ALLOWLIST_MARKER = "# bare-http-ok:"


def _scan() -> list[tuple[Path, int, str]]:
    """Return every ``raise HTTPException`` site without an allowlist marker.

    Returns:
        List of ``(path, line_no_1based, line_text)`` tuples for sites
        that still need conversion.
    """
    offenders: list[tuple[Path, int, str]] = []
    for path in sorted(_API_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if "raise HTTPException" not in line:
                continue
            # Allowlist comment may live on the same line, the
            # immediately preceding line, or anywhere in the few
            # lines above the raise (multi-line raise call).
            window = lines[max(0, idx - 4) : idx + 1]
            if any(_ALLOWLIST_MARKER in w for w in window):
                continue
            offenders.append((path, idx + 1, line.strip()))
    return offenders


def test_api_routes_have_no_unmarked_bare_http_exception() -> None:
    """Every ``raise HTTPException`` in pointlessql/api/ is allowlisted.

    Add the literal comment ``# bare-http-ok: <reason>`` on the line
    above (or any of the four lines above) the raise to opt a
    legitimate residual out of this lint.
    """
    offenders = _scan()
    if offenders:
        rendered = "\n".join(
            f"  {path.relative_to(_API_ROOT.parent.parent)}:{lineno}: {snippet}"
            for path, lineno, snippet in offenders
        )
        raise AssertionError(
            "Bare-string ``raise HTTPException`` sites found without "
            "``# bare-http-ok: <reason>`` allowlist marker:\n"
            f"{rendered}\n"
            "Either convert to a domain exception "
            "(see pointlessql/exceptions.py) or add the marker."
        )
