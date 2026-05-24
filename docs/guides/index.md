# Guides

Task-oriented walkthroughs. Three flavours:

1. **High-level recipes** — short, opinionated paths through
 common workflows. Read these first.
2. **Operator cookbook** — short recipes that link out to the
 long-form e2e walkthrough for each.
3. **Deterministic e2e walkthroughs** — 38 step-by-step
 playbooks, replayable by humans or by Claude Code through the
 Playwright MCP browser tools. Source of truth for every UI
 surface.

## High-level recipes

| Recipe | What you'll learn |
|---|---|
| **[Agent bring-up](agent-bring-up.md)** | Wire a brand-new Hermes agent to PointlesSQL end-to-end — install plugin, mint API keys, register the cron job, watch the first run land in the audit cockpit. |
| **[Operator cookbook](operator-cookbook.md)** | Twenty things an operator does in a typical week, each linking to the deep walkthrough. |
| **[Troubleshooting](troubleshooting.md)** | Common errors and how to fix them. Mined from real bug reports and the codebase's "BUG-NN-NN" markers. |
| **[FAQ](faq.md)** | The questions a new reader actually asks. |
| **[Jobs](jobs.md)** | The in-process scheduler — author a `python` job kind, register a cron, hook the failure webhook. |

## E2E walkthroughs

The 38 walkthroughs under [`docs/e2e-walkthroughs/`](../e2e-walkthroughs/README.md)
are themed in the nav into five sub-sections. Each playbook is
a deterministic markdown file replayable by both humans and
Claude Code through Playwright MCP.

### Getting around (UI navigation)

[home.md](../e2e-walkthroughs/home.md) ·
[catalog-browsing.md](../e2e-walkthroughs/catalog-browsing.md) ·
[mobile.md](../e2e-walkthroughs/mobile.md) ·
[list-polish.md](../e2e-walkthroughs/list-polish.md) ·
[command-palette.md](../e2e-walkthroughs/command-palette.md) ·
[ux-overhaul.md](../e2e-walkthroughs/ux-overhaul.md) ·
[auth.md](../e2e-walkthroughs/auth.md) ·
[csrf.md](../e2e-walkthroughs/csrf.md) ·
[rate-limit.md](../e2e-walkthroughs/rate-limit.md) ·
[oidc.md](../e2e-walkthroughs/oidc.md)

### Working with data

[sql-editor.md](../e2e-walkthroughs/sql-editor.md) ·
[inline-editors.md](../e2e-walkthroughs/inline-editors.md) ·
[time-travel.md](../e2e-walkthroughs/time-travel.md) ·
[branches.md](../e2e-walkthroughs/branches.md) ·
[hermes_medallion.md](../e2e-walkthroughs/hermes_medallion.md) ·
[federation.md](../e2e-walkthroughs/federation.md) ·
[foreign-catalog-sync.md](../e2e-walkthroughs/foreign-catalog-sync.md) ·
[dashboards.md](../e2e-walkthroughs/dashboards.md) ·
[config-matrix.md](../e2e-walkthroughs/config-matrix.md) ·
[error-handling.md](../e2e-walkthroughs/error-handling.md) ·
[packaging.md](../e2e-walkthroughs/packaging.md)

### Notebooks + jobs

[notebook-editor.md](../e2e-walkthroughs/notebook-editor.md) ·
[notebook_full_walkthrough.md](../e2e-walkthroughs/notebook_full_walkthrough.md) ·
[notebook-jobs.md](../e2e-walkthroughs/notebook-jobs.md) ·
[jobs-dag.md](../e2e-walkthroughs/jobs-dag.md)

### Audit + lineage

[admin-audit.md](../e2e-walkthroughs/admin-audit.md) ·
[audit-sinks.md](../e2e-walkthroughs/audit-sinks.md) ·
[audit-reviewer-daily.md](../e2e-walkthroughs/audit-reviewer-daily.md) ·
[compliance-bot.md](../e2e-walkthroughs/compliance-bot.md) ·
[incident-responder.md](../e2e-walkthroughs/incident-responder.md) ·
[rollback.md](../e2e-walkthroughs/rollback.md) ·
[operational.md](../e2e-walkthroughs/operational.md) ·
[agent_drift_monitor.md](../e2e-walkthroughs/agent_drift_monitor.md)

### Agents + ML registry

[agent-ml-registry.md](../e2e-walkthroughs/agent-ml-registry.md) ·
[models-tab.md](../e2e-walkthroughs/models-tab.md) ·
[models-promotion.md](../e2e-walkthroughs/models-promotion.md) ·
[inference-lineage.md](../e2e-walkthroughs/inference-lineage.md) ·
[reflexive_tools.md](../e2e-walkthroughs/reflexive_tools.md)

## Replay convention

Every walkthrough has a deterministic shape:

1. **Setup** — preconditions ("auth.md walked first; admin@pql.test
 logged in; seed-e2e.py ran").
2. **Numbered steps** — each step has an `Action:` (terminal
 command or browser click) and an `Expect:` (assertion on
 rendered state).
3. **Failure modes** — the visible-error envelopes operators
 should see for the most common slips.

Claude Code through Playwright MCP can replay any walkthrough
end-to-end without human intervention; the
[`docs/e2e-walkthroughs/README.md`](../e2e-walkthroughs/README.md)
explains the harness.

When a sprint touches HTML or JS, the relevant walkthrough should
be replayed in a real browser before the sprint commits. The
[run-playbook-as-gate convention](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
is enforced by code review, not CI — is a candidate
for adding a Playwright nightly that diffs against the playbooks.
