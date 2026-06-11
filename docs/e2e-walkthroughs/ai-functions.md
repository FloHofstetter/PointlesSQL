# AI SQL functions walkthrough

> **Mode:** `browser` · **Surface:** /sql (ai_* scalar functions)

Exercise the LLM-backed SQL vocabulary: the deterministic `ai_mask`
without any provider, the unconfigured-provider error path, and —
when a provider key is present — a real `ai_classify` over a column.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- Part B needs **no** LLM configured (the default e2e stack).
- Part C needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` exported into
  the app container (or a workspace Lens provider credential) —
  skip it when absent and note the skip.

## Walkthrough

### Part A — ai_mask, no provider needed (1 step)

1. **Deterministic masking**.
   - Action: in `/sql` run
     `SELECT ai_mask('alice@example.com') AS masked`.
   - Assert: one row; the value does **not** contain
     `alice@example.com` (e-mail shape is redacted).

### Part B — clear error without a provider (1 step)

2. **Unconfigured provider fails loudly**.
   - Action: run `SELECT ai_query('say hi')`.
   - Assert: the editor surfaces an error mentioning
     "AI functions need a configured LLM provider" (not a DuckDB
     unknown-function error, not a hang).

### Part C — real classification (provider required, 2 steps)

3. **Classify a column**.
   - Action: run
     `SELECT name, ai_classify(name, 'fruit,animal') AS label FROM (VALUES ('apple'), ('dog'), ('apple')) t(name)`.
   - Assert: three rows; labels drawn from {fruit, animal};
     the two `apple` rows carry the same label (the per-query
     dedup cache answered the repeat without a second call).

4. **Budget guard**.
   - Action: set `POINTLESSQL_AI_FUNCTIONS_MAX_CALLS_PER_QUERY=2`
     on the app (restart), then run a SELECT applying `ai_query`
     over 3+ distinct values.
   - Assert: the query fails with the budget message naming the
     env var; lowering back / restarting restores normal runs.
