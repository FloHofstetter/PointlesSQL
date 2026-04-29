# ADR-0003 — Delta-Branching shallow-clone spike (Sprint 16.5.0)

Status: spike — informs Phase 16.5 product re-decision.

## Context

Phase 16.5 (Delta-Branching) sketches per-agent-run zero-copy
branches of UC schemas: every run gets its own private copy of
the target schema, promote-to-main goes through an approval,
discard is free.  The "zero-copy" claim rests on synthesising a
new Delta table whose Add actions reference the source's
existing parquet files — never copying bytes.

deltalake-python 1.5.0 has no first-class clone API.  This
spike (Sprint 16.5.0) tested the three plausible mechanisms and
documents what works.

## Test plan

Source table: two writes (`v=0`, `v=1`), 5 rows total, 2 parquet
files, 2 Add actions in `_delta_log`.

Three branch-creation paths tried:

| # | Approach | Mechanism |
|---|---|---|
| A | Absolute Add-action paths | `AddAction(path="/abs/.../part-XXX.parquet")` + `create_table_with_add_actions` |
| B | `file://` URI Add-action paths | `AddAction(path="file:///abs/.../part-XXX.parquet")` |
| C | Symlink + relative paths | `branch_dir/part-XXX.parquet` → symlink → source's parquet, then `AddAction(path="part-XXX.parquet")` |

Reproducer: `tmp/spike_16_5_0.py` (kept as evidence, not
committed — re-run via `uv run python <path>` to verify).

## Findings

### A. Absolute paths — ❌ NOT VIABLE

`create_table_with_add_actions(table_uri="/branch", add_actions=[
AddAction(path="/source/part-XXX.parquet", ...)])` accepts the
absolute path and writes it verbatim into
`branch/_delta_log/00…0.json`.  The Delta protocol allows
absolute paths in Add actions.

But the reader (delta-rs via deltalake-python) re-anchors the
path to the table root: it computes the parquet location as
`<table_uri> + <add.path>`, producing `/branch/source/part-XXX.parquet`
(non-existent) and raising `FileNotFoundError`.

This is a delta-rs limitation, not a Delta protocol issue.  The
Add.path field is treated as relative-to-table-root unconditionally.

### B. `file://` URIs — ❌ NOT VIABLE

Same failure mode as (A): the reader concatenates the URI as a
relative path, producing
`/branch_uri/file:/source/part-XXX.parquet` and raising the same
`FileNotFoundError`.  delta-rs does not parse the `file://`
scheme as an escape hatch from the relative-path treatment.

### C. Symlink + relative paths — ✅ WORKS LOCALLY

`branch/part-XXX.parquet → symlink → source/part-XXX.parquet`,
then `AddAction(path="part-XXX.parquet", ...)`.

Result:

- Branch reads identical data to source (`symlink_data_matches: true`,
  5 rows in source = 5 rows in branch).
- Append to branch produces a new parquet under `branch/` and
  bumps branch version → 1, source version stays 0
  (`symlink_source_unchanged: true`).
- Source's row count is unchanged after the branch is appended
  to (the writer follows the symlink only for read; new writes
  go through the branch's Delta protocol).

Storage cost: zero (symlinks are filesystem entries, ~tens of bytes).

**Cloud-storage limitation**: S3 / GCS / Azure Blob have no
symlink primitive.  Object stores treat keys as opaque strings.
To make (C) work on cloud, we would need to deep-copy parquet
files into the branch's prefix — losing the zero-copy story.

## Verdict

**Zero-copy branching as Phase 16.5 envisioned is NOT viable on
cloud storage with the current delta-rs reader.**  Three options
for the phase:

1. **Local-only branching** (symlink fallback): ship Phase 16.5
   for local-FS deployments only; document the cloud limitation;
   defer cloud support until delta-rs upstream supports absolute
   Add-action paths.  Phase 16.5 still ships its
   ``pql.branch / promote / discard`` API + Control-Room UI;
   ``CloudBranchUnsupported`` is raised when the source schema
   sits on S3/GCS/Azure.
2. **Deep-copy branching everywhere**: works on cloud + local,
   loses the zero-copy claim, larger storage cost.  Phase 16.5
   ships everywhere but the differentiator narrows to "isolated
   write target with promote/discard semantics" — still useful,
   weaker pitch.
3. **Hybrid**: symlink on local, deep-copy on cloud, transparent
   to user.  More code paths but covers both deployment shapes.
4. **Wait for delta-rs upstream**: open issue
   <https://github.com/delta-io/delta-rs/issues/2102> tracks
   absolute-path support.  Could be months; phase stays parked.

### Recommendation

Hybrid (3) for Phase 16.5 v1: symlink on local FS, deep-copy on
cloud, with a `cloud_branch_strategy: 'deep_copy' | 'error'`
setting in `pointlessql.yaml` so deployers can opt into the
storage cost or refuse cloud branching outright.  Per-call
`pql.branch(strategy="deep_copy")` overrides the setting.

This keeps the zero-copy story honest on the deployment that
matters most for early adopters (local dev with the reference
``./data`` storage_root) while giving cloud deployers a working
fallback rather than a dead feature.

## Rejected alternatives

- **Hardlinks instead of symlinks** (local FS): also works on
  Linux, but with cross-filesystem-mount limitation and no
  cloud-storage advantage either.  Symlinks are the standard
  shape; hardlinks add no value.
- **Custom Delta-log writer with absolute paths** (bypass
  `create_table_with_add_actions`): fragile, diverges from
  upstream, breaks on every delta-rs upgrade.  Punted.
- **Diff-and-replay promotion** (instead of pointer-swap): out
  of scope for v1; ROADMAP already documents pointer-swap as
  Sprint 16.5.4.
