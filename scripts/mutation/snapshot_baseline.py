#!/usr/bin/env python
r"""Turn ``mutmut results`` output into a committed baseline, or diff against it.

The nightly full run produces a fresh ``mutmut results`` dump; this script
aggregates it per module and either snapshots it to ``baseline.json`` or
compares a fresh dump against the committed baseline to surface mutants
that newly survive.

Usage::

    # snapshot (one-off, after a clean full run)
    uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py results \
        | python scripts/mutation/snapshot_baseline.py --write scripts/mutation/baseline.json

    # diff a fresh dump against the committed baseline (nightly)
    uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py results \
        | python scripts/mutation/snapshot_baseline.py --diff scripts/mutation/baseline.json

The results format is one ``<module>.<mangled_function>__mutmut_<n>: <status>``
line per mutant; the module key is everything up to the final dotted
component.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

# mutmut status string -> the bucket we track per module.
_BUCKET = {
    "survived": "survived",
    "killed": "killed",
    "not checked": "no_test",
    "timeout": "killed",
    "suspicious": "killed",
    "skipped": "no_test",
}


def _parse(lines: list[str]) -> tuple[dict[str, dict[str, int]], set[str]]:
    """Aggregate ``mutmut results`` lines per module.

    Args:
        lines: raw ``mutmut results`` output lines.

    Returns:
        A ``(per_module_counts, survivor_names)`` pair. ``per_module_counts``
        maps each module to its bucket tally; ``survivor_names`` is the flat
        set of surviving mutant names.
    """
    per_module: dict[str, dict[str, int]] = defaultdict(
        lambda: {"killed": 0, "survived": 0, "no_test": 0}
    )
    survivors: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if ": " not in line:
            continue
        name, _, status = line.rpartition(": ")
        bucket = _BUCKET.get(status.strip())
        if bucket is None:
            continue
        module = name.rsplit(".", 1)[0] if "." in name else name
        per_module[module][bucket] += 1
        if bucket == "survived":
            survivors.add(name)
    return dict(per_module), survivors


def _load_baseline(path: str) -> set[str]:
    """Return the set of survivor names recorded in a baseline file."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return set(data.get("survivors", []))


def main() -> int:
    """Snapshot or diff a ``mutmut results`` dump piped on stdin."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", metavar="PATH", help="write baseline.json to PATH")
    group.add_argument("--diff", metavar="PATH", help="diff stdin against the baseline at PATH")
    args = parser.parse_args()

    per_module, survivors = _parse(sys.stdin.readlines())

    if args.write:
        payload = {
            "modules": dict(sorted(per_module.items())),
            "survivors": sorted(survivors),
            "total_survivors": len(survivors),
        }
        with open(args.write, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        print(f"Wrote {args.write}: {len(survivors)} survivors across {len(per_module)} modules.")
        return 0

    baseline = _load_baseline(args.diff)
    new = sorted(survivors - baseline)
    fixed = sorted(baseline - survivors)
    print(f"Baseline survivors: {len(baseline)}; current: {len(survivors)}.")
    if fixed:
        print(f"\nNo longer surviving ({len(fixed)}):")
        for name in fixed:
            print(f"  - {name}")
    if new:
        print(f"\nNEWLY surviving ({len(new)}):")
        for name in new:
            print(f"  + {name}")
        return 1
    print("\nNo new survivors vs baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
