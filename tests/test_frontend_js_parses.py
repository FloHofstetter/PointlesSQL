"""smoke-parse the new Alpine helper JS modules.

The Discussion tab loads two JS modules via plain ``<script>``
tags.  Without a Playwright walkthrough, the cheapest verification
is parsing them through ``node -c`` so a typo in a closure or an
unmatched bracket lands a red CI run instead of a silently broken
typeahead in a browser.

If ``node`` is not on ``$PATH`` the test xfails — the parse gate
is best-effort, the browser-replay step in the close-out plan is
the canonical verification.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_FRONTEND_JS = Path(__file__).parent.parent / "frontend" / "js"

_PHASE_76_6_1_MODULES = (
    "mention_autocomplete.js",
    "comments_collapse.js",
)


@pytest.mark.parametrize("filename", _PHASE_76_6_1_MODULES)
def test_mention_autocomplete_js_module_parses(filename: str) -> None:
    """``node -c <module>`` exits 0 — syntactically valid JS."""
    node = shutil.which("node")
    if node is None:
        pytest.xfail("node not on PATH; relying on browser replay")
    path = _FRONTEND_JS / filename
    assert path.exists(), f"{filename} missing under frontend/js/"
    result = subprocess.run(
        [node, "-c", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"{filename} failed to parse:\n{result.stderr}"
