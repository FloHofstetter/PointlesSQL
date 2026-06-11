# Asset bundles walkthrough

> **Mode:** `browser` · **Surface:** /admin/bundles (+ CLI)

Exercise workspace-as-code: plan a YAML bundle, apply it, verify
idempotency, and round-trip via export.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first (admin).

## Walkthrough

### Part A — plan + apply (3 steps)

1. **Open the console**: `/admin` → card "Asset bundles" (or
   navigate to `/admin/bundles`).
   - Assert: YAML textarea + Plan/Apply controls.

2. **Plan a bundle**.
   - Action: paste
     ```yaml
     bundle:
       name: e2e-bundle
     jobs:
       - name: e2e-bundle-job
         cron: "0 6 * * *"
         kind: python
         config: {entry_point: nightly_entry}
     dashboards:
       - slug: e2e-bundle-dash
         title: E2E Bundle Dash
         widgets:
           - kind: markdown
             title: About
             markdown: "Managed by the e2e bundle."
     ```
     and click **Plan**.
   - Assert: the diff table lists both resources with action
     `create`; nothing exists yet.

3. **Apply**.
   - Action: click **Apply** (dry-run off).
   - Assert: outcome shows 2 created / 0 errors; `/jobs` lists
     `e2e-bundle-job` (paused state per spec default) and `/bi`
     lists the dashboard with the markdown widget.

### Part B — idempotency + export (3 steps)

4. **Re-apply is a no-op**: Plan again → both rows `unchanged`;
   Apply → 0 changes.

5. **Drift repair**: rename the job's cron in the UI (or edit the
   YAML's cron) → Plan shows `update` with the field change →
   Apply converges.

6. **Export round-trip**.
   - Action: in the export panel select the job + dashboard →
     export; copy the YAML, Plan it.
   - Assert: every row `unchanged` — export output is a fixed
     point. Optionally verify the CLI:
     `uv run pointlessql bundle plan bundle.yaml --run-as <admin-email>`.
