"""Comment/review bodies must render through an escape-first renderer.

User-authored markdown (comments, reviews) is bound into the DOM with
Alpine ``x-html``.  Binding the raw ``body_md`` is stored XSS — a comment
with ``<img src=x onerror=...>`` runs script for every viewer.  Every such
binding must wrap the value in an escape-first renderer
(``window.pqlRenderCitations`` / ``mdInline`` / ``renderedBody``).  This
scan fails if a raw binding is ever reintroduced.
"""

from __future__ import annotations

import pathlib
import re

_TEMPLATES = pathlib.Path("frontend/templates")
# Any x-html binding whose expression references a *_body_md field.
_BINDING = re.compile(r'x-html="([^"]*body_md[^"]*)"')
# Renderers that HTML-escape their input before producing markup.
_SAFE_RENDERERS = ("pqlRenderCitations(", "mdInline(", "renderedBody", "bodyRendered")


def test_no_raw_body_md_x_html_binding() -> None:
    """No template binds a raw user-markdown body straight into x-html."""
    offenders: list[str] = []
    for path in _TEMPLATES.rglob("*.html"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _BINDING.search(line)
            if match and not any(r in match.group(1) for r in _SAFE_RENDERERS):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, "raw body_md x-html bindings (stored-XSS risk):\n" + "\n".join(offenders)
