#!/usr/bin/env python3
"""Inventory the docs/ tree and emit a machine-readable TSV.

One row per markdown file under ``docs/``.  Drives the manual
audience+status classification in ``docs/internal/doc-audit.md`` and
the orphan-guard hook in ``scripts/check-doc-orphans.sh``.

Run from the repo root.  Re-run whenever doc files are added,
removed, or moved; the TSV is committed so diffs surface drift.

Columns (tab-separated):

    path             Repo-root-relative path to the markdown file.
    loc              Line count.
    title            Top-level ``# `` heading, or "(no title)".
    first_para       First non-blank, non-heading paragraph, single-
                     line, truncated to 200 chars.
    last_mod_date    Most-recent commit date in YYYY-MM-DD form.
    last_mod_author  Most-recent commit author name.
    in_mkdocs_nav    "true" / "false" — whether the path appears
                     anywhere in ``mkdocs.yml``.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path("docs")
MKDOCS = pathlib.Path("mkdocs.yml")
OUTPUT = pathlib.Path("docs/internal/doc-audit.tsv")

# Match any path-shaped substring ending in ``.md`` so mixed-case
# ``README.md`` plus lower-case page paths both register.
NAV_PATH_RE = re.compile(r"[A-Za-z0-9_/-]+\.md")
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")


def _strip_front_matter(text: str) -> tuple[dict[str, str], str]:
    r"""Split ``---\n…\n---`` YAML front-matter off the start of ``text``.

    Returns ``(meta, body)``.  ``meta`` is an empty dict when the file
    has no front-matter or the closing ``---`` is missing.  Front-matter
    parsing is intentionally a flat ``key: value`` shallow read; doc
    files do not use nested YAML.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body


def _heading_and_first_para(text: str) -> tuple[str, str]:
    """Return ``(title, first_paragraph)`` extracted from a markdown body.

    Front-matter is stripped first so files like ADR-0004 (which carry
    ``title:`` in front-matter and rely on a separate ``# ``-heading
    for the rendered title) still classify correctly.  The title is
    the first ``# ``-prefixed line in the body; falls back to the
    front-matter ``title:`` if no body heading is present; falls back
    to "(no title)" otherwise.  The first paragraph is the next block
    of non-empty, non-heading lines joined into a single line and
    truncated to 200 characters.
    """
    meta, body = _strip_front_matter(text)
    title = "(no title)"
    para_lines: list[str] = []
    in_para = False
    for raw in body.splitlines():
        line = raw.rstrip()
        if title == "(no title)":
            m = HEADING_RE.match(line)
            if m:
                title = m.group(1)
                continue
        if not in_para:
            if line and not line.startswith(("#", "---", "> ", "`")):
                in_para = True
                para_lines.append(line)
        else:
            if not line:
                break
            if line.startswith("#"):
                break
            para_lines.append(line)
    if title == "(no title)" and "title" in meta:
        title = meta["title"]
    para = " ".join(para_lines)
    para = re.sub(r"\s+", " ", para).strip()
    if len(para) > 200:
        para = para[:197].rstrip() + "..."
    return title, para or "(no body)"


def _git_log_field(path: pathlib.Path, fmt: str) -> str:
    """Return the most-recent commit's ``--format=<fmt>`` for ``path``.

    Empty string if the file is not yet tracked (e.g. about to be
    committed).
    """
    out = subprocess.run(
        ["git", "log", "-1", f"--format={fmt}", "--", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def _tsv_safe(value: str) -> str:
    """Strip tab and newline characters that would corrupt the TSV layout."""
    return value.replace("\t", " ").replace("\n", " ")


def _nav_paths(mkdocs_yml: pathlib.Path) -> set[str]:
    """Collect every ``*.md`` path referenced in ``mkdocs.yml``.

    Case-insensitive so ``README.md`` registers alongside lower-case
    pages.  Returns a set of paths relative to ``docs/`` (the mkdocs
    docs-dir convention), matching the format produced by
    ``str(path.relative_to(ROOT))``.
    """
    text = mkdocs_yml.read_text(encoding="utf-8")
    return {m.group(0) for m in NAV_PATH_RE.finditer(text)}


def main() -> int:
    """Emit the TSV inventory to stdout *and* ``docs/internal/doc-audit.tsv``."""
    if not ROOT.is_dir():
        print(f"docs-inventory: {ROOT} not found", file=sys.stderr)
        return 1
    if not MKDOCS.is_file():
        print(f"docs-inventory: {MKDOCS} not found", file=sys.stderr)
        return 1

    nav = _nav_paths(MKDOCS)

    header = "path\tloc\ttitle\tfirst_para\tlast_mod_date\tlast_mod_author\tin_mkdocs_nav"
    rows: list[str] = [header]
    for md in sorted(ROOT.rglob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        title, para = _heading_and_first_para(text)
        loc = text.count("\n") + (0 if text.endswith("\n") else 1)
        nav_key = str(md.relative_to(ROOT))
        in_nav = nav_key in nav
        date = _git_log_field(md, "%cs") or "(untracked)"
        author = _git_log_field(md, "%an") or "(untracked)"
        rows.append(
            "\t".join(
                _tsv_safe(c)
                for c in (
                    str(md),
                    str(loc),
                    title,
                    para,
                    date,
                    author,
                    "true" if in_nav else "false",
                )
            )
        )

    body = "\n".join(rows) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(body, encoding="utf-8")
    sys.stdout.write(body)
    print(f"\n=== wrote {OUTPUT} ({len(rows) - 1} rows) ===", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
