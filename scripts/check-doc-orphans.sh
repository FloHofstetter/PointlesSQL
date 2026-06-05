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
import fnmatch
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


def _block_patterns(text: str, key: str) -> set[str]:
    """Return the docs-relative path patterns declared in a YAML block-scalar.

    Honors the same glob patterns mkdocs itself accepts — ``internal/*``,
    ``e2e-walkthroughs/*`` — as well as explicit ``foo.md`` entries, so a
    whole maintainer-only tree can be declared with one line instead of
    listing every file.  Strips a single leading ``/`` so ``/internal/foo.md``
    (the not_in_nav form) and ``internal/*`` (the exclude_docs form) both
    compare cleanly against the docs-relative paths we get from ``rglob``.
    """
    patterns: set[str] = set()
    for m in INLINE_BLOCK_RE.finditer(text):
        if m.group(1) != key:
            continue
        for raw in m.group(2).splitlines():
            line = raw.strip()
            if not line:
                continue
            patterns.add(line.lstrip('/'))
    return patterns


text = MKDOCS.read_text(encoding='utf-8')
# Exact `.md` paths mentioned anywhere in mkdocs.yml — this is how real
# `nav:` entries get collected.
nav_paths = {m.group(0) for m in NAV_PATH_RE.finditer(text)}
# Glob (or exact) patterns from the two opt-out blocks; matched with
# fnmatch so they honor the same wildcard semantics mkdocs applies.
opt_out_patterns = _block_patterns(text, 'not_in_nav') | _block_patterns(text, 'exclude_docs')

orphans: list[str] = []
for md in sorted(ROOT.rglob('*.md')):
    relative = str(md.relative_to(ROOT))
    if relative in nav_paths:
        continue
    if any(fnmatch.fnmatch(relative, pattern) for pattern in opt_out_patterns):
        continue
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
