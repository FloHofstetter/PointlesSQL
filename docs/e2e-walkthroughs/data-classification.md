# Data classification walkthrough

> **Mode:** `browser` · **Surface:** /admin/classification + governed reads

Exercise the tag-policy + PII-scan loop end to end: scan a seeded
table, watch the scanner tag a column, add a `pii → mask` rule, and
verify a non-owner's SELECT comes back masked while an admin reads
raw.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first (admin).
- A second non-admin user exists with `SELECT` on the target table
  (grant via the table's Permissions card if needed).
- A seeded table with an e-mail-shaped column (the steps call it
  `e2e.demo.customers` with column `email` — substitute or create
  one from a notebook).

## Walkthrough

### Part A — scan (2 steps)

1. **Open the console**.
   - Action: `/admin` → card "Data classification".
   - Assert: heading "Data classification", empty rules table with
     the starter hint, and the "PII scan" card.

2. **Scan the table**.
   - Action: enter the FQN under "…or a single table", click
     "Scan now".
   - Assert: findings table lists `email` with kind `email` and
     badge `tagged`; re-running the scan flips the badge to
     `already curated` (additive-only).

### Part B — rule + enforcement (3 steps)

3. **Create the masking rule**.
   - Action: "New rule" — key `pii`, effect `mask`, expression
     `redact`; create.
   - Assert: the rule row appears, active.

4. **Non-owner reads masked**.
   - Action: as the non-admin user, run
     `SELECT email FROM e2e.demo.customers LIMIT 3` in `/sql`.
   - Assert: every value renders `***` — no raw e-mail leaks; the
     same masking holds in a notebook SQL cell.

5. **Admin reads raw**.
   - Action: as admin, run the same SELECT.
   - Assert: raw e-mails (admins and table owners are exempt).

### Part C — lifecycle (1 step)

6. **Deactivate restores raw reads**.
   - Action: toggle the rule to `inactive`; re-run the non-admin
     SELECT (allow ~15 s for the rule cache TTL).
   - Assert: raw values return; deleting the rule keeps it that
     way.
