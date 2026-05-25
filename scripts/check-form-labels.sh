#!/usr/bin/env bash
# Form-label drift guard.
#
# Counts <input>/<select>/<textarea> elements in frontend/templates/
# that lack any of:
#   - aria-label="..." / Alpine x-bind:aria-label / :aria-label
#   - aria-labelledby="..."
#   - a sibling <label for="<id>"> in the same file (lexical match)
#   - a wrapping <label>…</label> (WCAG wrapped-label pattern)
#
# Excluded form controls (no label needed):
#   - type="hidden"  (CSRF tokens, state)
#   - type="submit" / "button" / "reset" / "image"  (button text serves)
#
# Fails if the count exceeds FORM_LABEL_THRESHOLD (default 75; raise only
# with a written justification in the commit body).  Baseline after W8 is
# ~63 — keep the slack tight so new regressions surface fast.

set -euo pipefail

THRESHOLD="${FORM_LABEL_THRESHOLD:-75}"

python3 - "$THRESHOLD" <<'PY'
import re
import pathlib
import sys

threshold = int(sys.argv[1])

ROOT = pathlib.Path('frontend/templates')
if not ROOT.is_dir():
    print(f'form-label check: {ROOT} not found; skipping', file=sys.stderr)
    sys.exit(0)

INPUT_RE = re.compile(r'<(input|select|textarea)\b[^>]*>', re.IGNORECASE | re.DOTALL)
JINJA_COMMENT_RE = re.compile(r'\{#.*?#\}', re.DOTALL)
HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


def _strip_comments(text: str) -> str:
    """Replace Jinja + HTML comments with same-length whitespace so line
    numbers and offsets stay stable; prevents false-positive matches on
    `<input>` / `<select>` tokens that appear inside docstrings.
    """
    def _blank(m: re.Match) -> str:
        return re.sub(r'[^\n]', ' ', m.group(0))
    text = JINJA_COMMENT_RE.sub(_blank, text)
    text = HTML_COMMENT_RE.sub(_blank, text)
    return text
TYPE_RE = re.compile(r'\btype\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ID_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ARIA_LABEL_RE = re.compile(r'\b(?:x-bind:)?aria-label(?:ledby)?\b|\s:aria-label\b', re.IGNORECASE)
LABEL_FOR_RE = re.compile(
    r'<label\b[^>]*\bfor\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
EXCLUDED_TYPES = {'hidden', 'submit', 'button', 'reset', 'image'}

unlabeled: list[tuple[str, int, str]] = []
for html in sorted(ROOT.rglob('*.html')):
    text = _strip_comments(html.read_text(encoding='utf-8', errors='replace'))
    label_for_ids = set(LABEL_FOR_RE.findall(text))
    for m in INPUT_RE.finditer(text):
        snippet = m.group(0)
        type_m = TYPE_RE.search(snippet)
        if type_m and type_m.group(1).lower() in EXCLUDED_TYPES:
            continue
        if ARIA_LABEL_RE.search(snippet):
            continue
        id_m = ID_RE.search(snippet)
        if id_m and id_m.group(1) in label_for_ids:
            continue
        # Wrapped-label heuristic: <label>…<input>…</label>
        pre = text[max(0, m.start() - 400):m.start()]
        post = text[m.end():m.end() + 400]
        last_open = pre.rfind('<label')
        last_close = pre.rfind('</label>')
        if last_open > last_close and '</label>' in post[:400]:
            continue
        line_no = text[:m.start()].count('\n') + 1
        unlabeled.append((str(html), line_no, snippet[:100].replace('\n', ' ')))

count = len(unlabeled)
if count > threshold:
    print(
        f'Form-label drift: {count} unlabeled form controls (threshold {threshold})',
        file=sys.stderr,
    )
    print(
        '\nFirst 25 offenders (path:line  snippet):',
        file=sys.stderr,
    )
    for path, line, snippet in unlabeled[:25]:
        print(f'  {path}:{line}  {snippet}', file=sys.stderr)
    if count > 25:
        print(f'  ... and {count - 25} more', file=sys.stderr)
    print(
        '\nFix the new offender(s) with either:\n'
        '  - <label class="form-label" for="X">…</label><input id="X" …>\n'
        '  - or aria-label="…" on the input itself (for icon-/column-labeled cells).\n'
        'See frontend/templates/_macros/labeled_input.html.',
        file=sys.stderr,
    )
    sys.exit(1)
print(f'Form-label check: {count} unlabeled controls (threshold {threshold})')
PY
