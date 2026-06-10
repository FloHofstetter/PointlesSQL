#!/usr/bin/env python
"""Split the pre-W3 CHANGELOG.md into per-cluster dev-log files.

Reads a backup of the original CHANGELOG.md (default
``/tmp/CHANGELOG_pre_w3.md``) and partitions every ``Phase NN``-keyed
section into the cluster file it belongs to under
``docs/internal/dev-log/<cluster-id>-<slug>.md``.

Section detection handles two CHANGELOG-history shapes:

1. **Modern bullet form** (most of the file): a top-level bullet
   ``- **Phase NN[.M[letter]] — title (date, rcXX → rcYY).**`` followed
   by indented body until the next ``- **`` or section break.

2. **Older H3 form** (CHANGELOG lines 6625+): a ``### <type> — Phase NN
   <title>`` heading followed by body until the next ``### `` or
   ``## ``.

Each captured section is appended to its target cluster file together
with a small ``> from CHANGELOG.md (bucket: <Changed|Added|Fixed|...>)``
breadcrumb so the original-bucket context is not lost.

Lossless-checkable: the sum of body bytes in the dev-log files plus
the per-file YAML frontmatter overhead should approximate the original
CHANGELOG body bytes within a few percent.

Usage::

    uv run python scripts/devlog-split.py [--source /tmp/CHANGELOG_pre_w3.md]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLUSTERS_PATH = REPO_ROOT / "scripts" / "clusters.json"
DEFAULT_SOURCE = pathlib.Path("/tmp/CHANGELOG_pre_w3.md")
DEVLOG_DIR = REPO_ROOT / "docs" / "internal" / "dev-log"

MODERN_BULLET_RE = re.compile(r"^- \*\*Phase (\d+)")
OLDER_HEADING_RE = re.compile(r"^### .*?Phase (\d+)")
BUCKET_RE = re.compile(r"^### (?!.*Phase)([A-Z][A-Za-z]+)\s*$")
PHASE_NUMBER_RE = re.compile(r"Phase (\d+)")


def parse_phase_ranges(clusters: list[dict]) -> dict[int, str]:
    """Return a mapping ``phase_int -> cluster_id`` covering all phases.

    Cluster ``phases`` strings are ranges like ``"0-7"``, ``"95-106"``
    or singletons like ``"17"``.  Phases not explicitly listed (e.g.
    Phase 45-50, Phase 69) are assigned to the cluster whose range is
    closest below (chronological fall-through).
    """
    mapping: dict[int, str] = {}
    explicit_phases: list[tuple[int, str]] = []
    for c in clusters:
        ph = c["phases"]
        if "-" in ph:
            lo_s, hi_s = ph.split("-", 1)
            # Strip ".5" sub-versions for integer mapping.
            lo = int(lo_s.split(".")[0])
            hi = int(hi_s.split(".")[0])
        else:
            lo = hi = int(ph.split(".")[0])
        for n in range(lo, hi + 1):
            mapping[n] = c["id"]
        explicit_phases.append((hi, c["id"]))
    # Fill gaps (e.g. Phase 45-50, Phase 69) by picking the cluster
    # whose hi-range is closest below the gap phase.
    explicit_phases.sort()
    max_phase = max(hi for hi, _ in explicit_phases)
    for n in range(max_phase + 1):
        if n in mapping:
            continue
        fallback_id = explicit_phases[0][1]
        for hi, cid in explicit_phases:
            if hi < n:
                fallback_id = cid
        mapping[n] = fallback_id
    return mapping


def cluster_filename(cluster: dict) -> pathlib.Path:
    """Compose ``<id>-<slug>.md`` filename inside DEVLOG_DIR."""
    return DEVLOG_DIR / f"{cluster['id']}-{cluster['slug']}.md"


def write_cluster_files(
    clusters: list[dict],
    sections_by_cluster: dict[str, list[str]],
) -> None:
    """Write all cluster dev-log files under DEVLOG_DIR."""
    DEVLOG_DIR.mkdir(parents=True, exist_ok=True)
    for c in clusters:
        sections = sections_by_cluster.get(c["id"], [])
        frontmatter = (
            "---\n"
            f'title: "Cluster {c["id"]} — {c["name"]} (dev-log)"\n'
            "audience: contributor\n"
            f'cluster_id: "{c["id"]}"\n'
            f'phases: "{c["phases"]}"\n'
            f'closed: "{c["closed"]}"\n'
            "---\n\n"
        )
        intro = (
            f"# Cluster {c['id']} — {c['name']} (dev-log)\n\n"
            f"> {c['synopsis']}\n\n"
            "These entries were materialised from the pre-W3 "
            "``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan "
            "W3, 2026-05-26).  They preserve the original phase-keyed "
            "narrative for contributors who want richer commit-level "
            "context than the auto-generated per-cluster CHANGELOG "
            "section provides.\n\n"
            "---\n\n"
        )
        body = (
            "\n".join(sections)
            if sections
            else (
                "_No sections from the pre-W3 CHANGELOG mapped to this "
                "cluster.  Earlier history is captured in the "
                "auto-generated CHANGELOG section instead._\n"
            )
        )
        cluster_filename(c).write_text(frontmatter + intro + body)


def main() -> int:
    """Split the devlog backup into per-cluster pages and return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=DEFAULT_SOURCE,
        help="Path to backup of the pre-W3 CHANGELOG.md",
    )
    args = parser.parse_args()
    if not args.source.exists():
        sys.stderr.write(f"error: source file not found: {args.source}\n")
        return 1

    clusters = json.loads(CLUSTERS_PATH.read_text())
    phase_to_cluster = parse_phase_ranges(clusters)

    text = args.source.read_text()
    lines = text.split("\n")

    # Section assembly state.
    sections_by_cluster: dict[str, list[str]] = defaultdict(list)
    current_bucket = "Misc"
    current_section: list[str] = []
    current_phase: int | None = None
    skip_until_first_section = True

    def flush() -> None:
        nonlocal current_section, current_phase
        if current_phase is None or not current_section:
            current_section = []
            current_phase = None
            return
        cluster_id = phase_to_cluster.get(current_phase)
        if cluster_id is None:
            sys.stderr.write(
                f"warn: Phase {current_phase} not mapped to any cluster — skipping section\n"
            )
            current_section = []
            current_phase = None
            return
        breadcrumb = f"> from CHANGELOG.md (bucket: **{current_bucket}**)\n\n"
        body = "\n".join(current_section).rstrip() + "\n"
        sections_by_cluster[cluster_id].append(breadcrumb + body)
        current_section = []
        current_phase = None

    for line in lines:
        # Skip the original top headings until first real section.
        if skip_until_first_section:
            if MODERN_BULLET_RE.match(line) or OLDER_HEADING_RE.match(line):
                skip_until_first_section = False
            elif m := BUCKET_RE.match(line):
                current_bucket = m.group(1)
                continue
            else:
                continue

        # Bucket transition (Changed/Added/Fixed/...) flushes current.
        bucket_match = BUCKET_RE.match(line)
        if bucket_match:
            flush()
            current_bucket = bucket_match.group(1)
            continue

        # Modern bullet section start.
        modern_match = MODERN_BULLET_RE.match(line)
        if modern_match:
            flush()
            current_phase = int(modern_match.group(1))
            current_section.append(line)
            continue

        # Older H3 heading section start (### Closed — Phase NN ...).
        older_match = OLDER_HEADING_RE.match(line)
        if older_match:
            flush()
            current_phase = int(older_match.group(1))
            # Treat the H3 itself as a "Closed"/"Added" bucket label
            # extracted from the heading prefix.
            prefix_match = re.match(r"^### (\w+)", line)
            if prefix_match:
                current_bucket = prefix_match.group(1)
            current_section.append(line)
            continue

        # Body line of the current section.
        if current_phase is not None:
            current_section.append(line)

    flush()

    write_cluster_files(clusters, sections_by_cluster)

    total_sections = sum(len(v) for v in sections_by_cluster.values())
    file_count = len(clusters)
    print(
        f"Wrote {file_count} dev-log files under {DEVLOG_DIR} "
        f"({total_sections} sections classified)"
    )
    for c in clusters:
        n = len(sections_by_cluster.get(c["id"], []))
        path = cluster_filename(c).relative_to(REPO_ROOT)
        size = cluster_filename(c).stat().st_size
        print(f"  {c['id']} {path}: {n:>3} sections, {size:>6} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
