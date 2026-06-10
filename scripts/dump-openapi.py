#!/usr/bin/env python
"""Dump pointlessql's OpenAPI schema to docs/reference/_generated/.

The neoteroi-mkdocs OAD plugin renders ``docs/reference/api/openapi.md``
from a checked-in ``openapi.json``; the file lives under
``docs/reference/_generated/`` to keep generated artefacts visually
separate from hand-written reference pages.

A pre-commit hook (``id: dump-openapi``) regenerates the JSON when
any ``pointlessql/api/*.py`` file changes so the rendered REST
reference cannot drift from the FastAPI app's actual route surface.

The JSON is written with ``sort_keys=True`` + 2-space indent so the
diff is stable across re-runs (FastAPI's ``app.openapi()`` returns
dicts in insertion order; without sort the diff would be noisy).

Usage::

    uv run python scripts/dump-openapi.py
"""

from __future__ import annotations

import json
import pathlib

from pointlessql.api.main import app

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "reference" / "_generated" / "openapi.json"


def main() -> int:
    """Write the app's OpenAPI schema snapshot and return an exit code."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUTPUT_PATH.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} "
        f"({OUTPUT_PATH.stat().st_size} bytes, "
        f"{len(schema.get('paths', {}))} paths)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
