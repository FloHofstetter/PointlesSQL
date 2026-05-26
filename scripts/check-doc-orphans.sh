#!/usr/bin/env bash
# Documentation orphan-guard.
#
# Asserts every markdown file under ``docs/`` is either:
#   - reachable from ``mkdocs.yml`` (via a ``nav:`` entry), OR
#   - listed in ``mkdocs.yml`` ``not_in_nav:`` (static-asset
#     companion of a rendered page), OR
#   - listed in ``mkdocs.yml`` ``exclude_docs:`` (shipped on disk
#     for repo viewing but not rendered to HTML; reserved for
#     maintainer-only artifacts under ``docs/internal/``).
#
# Fails if the orphan count exceeds ``DOC_ORPHAN_THRESHOLD``
# (default 18; baseline after W1.5 is 18 e2e-walkthrough files
# that stay orphan until W5 introduces theme-grouped sub-nav).
#
# Rationale: this is the W7 link-hygiene gate's *cheap predecessor*.
# It catches the trivial "added a new doc, forgot to wire it into
# nav" mistake on every commit instead of waiting for the strict
# mkdocs build to surface it in CI.

set -euo pipefail

THRESHOLD="${DOC_ORPHAN_THRESHOLD:-18}"

python3 - "$THRESHOLD" <<'PY'
import pathlib
import re
import sys


threshold = int(sys.argv[1])

ROOT = pathlib.Path('docs')
MKDOCS = pathlib.Path('mkdocs.yml')

if not ROOT.is_dir():
    print(f'doc-orphan check: {ROOT} not found; skipping', file=sys.stderr)
    sys.exit(0)
if not MKDOCS.is_file():
    print(f'doc-orphan check: {MKDOCS} not found; skipping', file=sys.stderr)
    sys.exit(0)

NAV_PATH_RE = re.compile(r'[A-Za-z0-9_/-]+\.md')
INLINE_BLOCK_RE = re.compile(
    r'^(not_in_nav|exclude_docs):\s*\|\s*\n((?:[ \t]+\S.*\n?)+)',
    re.MULTILINE,
)


def _block_paths(text: str, key: str) -> set[str]:
    """Return the set of docs-relative paths declared in a YAML block-scalar.

    Strips a single leading ``/`` so ``/internal/foo.md`` (the form
    mkdocs documents for not_in_nav) and ``internal/foo.md`` (the form
    mkdocs documents for exclude_docs) both compare cleanly against
    the docs-relative paths we get from ``rglob``.
    """
    paths: set[str] = set()
    for m in INLINE_BLOCK_RE.finditer(text):
        if m.group(1) != key:
            continue
        for raw in m.group(2).splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.endswith('.md'):
                paths.add(line.lstrip('/'))
    return paths


text = MKDOCS.read_text(encoding='utf-8')
nav_paths = {m.group(0) for m in NAV_PATH_RE.finditer(text)}
not_in_nav = _block_paths(text, 'not_in_nav')
excluded = _block_paths(text, 'exclude_docs')

# `not_in_nav` and `exclude_docs` entries may have leading slashes
# stripped above; nav entries we collect via the more permissive
# inline regex.  Normalise everything before comparing.
declared = nav_paths | {p.lstrip('/') for p in not_in_nav | excluded}

orphans: list[str] = []
for md in sorted(ROOT.rglob('*.md')):
    relative = str(md.relative_to(ROOT))
    if relative not in declared:
        orphans.append(relative)

count = len(orphans)
if count > threshold:
    print(
        f'Doc orphan drift: {count} markdown file(s) under docs/ are not '
        f'declared in mkdocs.yml (threshold {threshold})',
        file=sys.stderr,
    )
    print(
        '\nFix the new offender(s) by either:\n'
        '  - adding a nav entry in mkdocs.yml under the right group, OR\n'
        '  - adding the path to mkdocs.yml not_in_nav:  (for static\n'
        '    assets referenced from a rendered page), OR\n'
        '  - adding the path to mkdocs.yml exclude_docs:  (for\n'
        '    maintainer-only artifacts under docs/internal/).\n'
        '\nSee docs/internal/doc-site-ia.md for the contract.\n'
        '\nOrphan list:',
        file=sys.stderr,
    )
    for path in orphans[:30]:
        print(f'  {path}', file=sys.stderr)
    if count > 30:
        print(f'  ... and {count - 30} more', file=sys.stderr)
    sys.exit(1)

print(
    f'Doc orphan check: {count} orphan markdown file(s) (threshold {threshold})'
)
PY
