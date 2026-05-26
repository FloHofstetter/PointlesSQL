#!/usr/bin/env python
"""Regenerate CHANGELOG.md from the cluster-map.

Iterates ``scripts/clusters.json`` and, per cluster, invokes
``git cliff <from>..<to> --strip header`` to render the body for
that commit range.  Each cliff section is wrapped with a
``## [Cluster <id> — <name>] - YYYY-MM-DD`` heading and a one-line
synopsis pulled from ``clusters.json``.

The first cluster has no ``from`` boundary (its lower bound is the
repository root); the wrapper omits the ``from..`` prefix in that
case so cliff renders the entire prefix history.

Output is written to ``CHANGELOG.md`` at the repo root.  An
``## [Unreleased]`` stub is prepended for future commits that land
before the next cluster boundary is defined.

Usage::

    uv run python scripts/regen-changelog.py

Re-runnable: the output is deterministic given the same git history
+ clusters.json content.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLUSTERS_PATH = REPO_ROOT / "scripts" / "clusters.json"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
CLIFF_CONFIG = REPO_ROOT / "cliff.toml"

HEADER = """# Changelog

All notable changes to this project will be documented in this file.

The CHANGELOG is auto-generated from Conventional Commits via
[git-cliff](https://git-cliff.org/), grouped into per-cluster release
sections.  Cluster boundaries live in ``scripts/clusters.json``;
re-generate with ``uv run python scripts/regen-changelog.py``.

The full per-rc dev-log lives under ``docs/internal/dev-log/`` for
contributors who need finer commit-level granularity.

## [Unreleased]

<!-- Future commits land here until the next cluster boundary is
defined in ``scripts/clusters.json``. -->

"""


def run_cliff(commit_range: str) -> str:
    """Invoke git-cliff for the given range and return the body output."""
    cmd = [
        "uvx", "--from", "git-cliff", "git-cliff",
        commit_range,
        "--config", str(CLIFF_CONFIG),
        "--strip", "header",
        # Suppress per-tag sub-sectioning inside a cluster range.  The
        # repo carries v0.1.0rc1/rc2/rc3 tags from the Sprint 39 release
        # engineering trial; without --ignore-tags those would split
        # Cluster 02's body into 3 extra `## [vX]` sub-headings on top
        # of the cluster heading the wrapper injects.
        "--ignore-tags", "v.*",
        "--output", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        sys.stderr.write(f"git-cliff failed for range {commit_range!r}:\n")
        sys.stderr.write(result.stderr)
        sys.exit(1)
    return result.stdout


def wrap_cluster(cluster: dict, prev_to: str | None) -> str:
    """Render one cluster section.

    The range is ``<prev_to>..<to>`` for clusters with a predecessor,
    or just ``<to>`` for the first cluster (renders root-to-to).
    """
    range_arg = f"{prev_to}..{cluster['to_commit']}" if prev_to else cluster["to_commit"]
    body = run_cliff(range_arg)
    # Replace cliff's '## [Unreleased]' marker with our cluster heading.
    heading = (
        f"## [Cluster {cluster['id']} — {cluster['name']}] "
        f"- {cluster['closed']}"
    )
    body = re.sub(r"^## \[Unreleased\]", heading, body, count=1, flags=re.MULTILINE)
    synopsis = f"> {cluster['synopsis']}\n\n"
    # Insert synopsis after the heading line.
    body = body.replace(heading, f"{heading}\n\n{synopsis}", 1)
    # cliff trims trailing newlines; normalise to two for separation.
    return body.rstrip() + "\n\n"


def commit_timestamp(commit: str) -> int:
    """Return committer-date Unix timestamp of *commit*."""
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", commit],
        capture_output=True, text=True, cwd=REPO_ROOT, check=True,
    )
    return int(out.stdout.strip())


def compute_from(cluster: dict, all_clusters: list[dict]) -> str | None:
    """Pick the previous cluster's to_commit by chronological order.

    Some phases closed out of phase-number order (Phase 17 polish landed
    AFTER Phase 20 close on the same day), so iterating ``clusters`` by
    list index would produce empty ranges and double-count commits.
    Instead, pick the chronologically-most-recent ``to_commit`` from
    any OTHER cluster that is strictly older than the current cluster's
    ``to_commit``.
    """
    target_ts = commit_timestamp(cluster["to_commit"])
    candidates = [
        (commit_timestamp(c["to_commit"]), c["to_commit"])
        for c in all_clusters
        if c["id"] != cluster["id"]
    ]
    older = [(ts, sha) for ts, sha in candidates if ts < target_ts]
    if not older:
        return None
    older.sort()
    return older[-1][1]


def main() -> int:
    clusters = json.loads(CLUSTERS_PATH.read_text())
    parts = [HEADER]
    # Output newest-first (ADR-0009 D1 + Keep-a-Changelog convention).
    # Sort clusters by commit timestamp descending so the output order
    # is independent of clusters.json list ordering.
    sorted_clusters = sorted(
        clusters,
        key=lambda c: commit_timestamp(c["to_commit"]),
        reverse=True,
    )
    for cluster in sorted_clusters:
        prev_to = compute_from(cluster, clusters)
        parts.append(wrap_cluster(cluster, prev_to))
    CHANGELOG_PATH.write_text("".join(parts))
    print(f"Wrote {CHANGELOG_PATH} ({len(''.join(parts))} bytes, "
          f"{len(clusters)} cluster sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
