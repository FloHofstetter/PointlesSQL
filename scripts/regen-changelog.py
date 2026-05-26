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


def main() -> int:
    clusters = json.loads(CLUSTERS_PATH.read_text())
    parts = [HEADER]
    prev_to: str | None = None
    # Newest-first: ADR-0009 D1 says release notes scan newest→oldest,
    # which is also the Keep-a-Changelog convention.  The cluster list
    # is stored oldest-first (chronological) for readability and is
    # reversed here for output ordering.
    for cluster in reversed(clusters):
        # Determine the previous cluster's to_commit by index lookup.
        idx = clusters.index(cluster)
        prev_to = clusters[idx - 1]["to_commit"] if idx > 0 else None
        parts.append(wrap_cluster(cluster, prev_to))
    CHANGELOG_PATH.write_text("".join(parts))
    print(f"Wrote {CHANGELOG_PATH} ({len(''.join(parts))} bytes, "
          f"{len(clusters)} cluster sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
