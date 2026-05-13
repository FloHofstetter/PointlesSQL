## Summary

<!-- Briefly describe what this PR does and why. -->

## Test plan

<!-- How did you test this? What edge cases did you consider? -->

- [ ] Unit tests pass (`uv run pytest -m 'not integration'`)
- [ ] Linting passes (`uv run ruff check . && uv run ruff format --check .`)
- [ ] Type check passes (`uv run pyright`)
- [ ] Docstring lint passes (`uv run pydoclint pointlessql`)
- [ ] File-size budget holds (`bash scripts/check-file-size-budget.sh`)
- [ ] Pyright budget holds (`bash scripts/check-pyright-budget.sh`)

## Database migrations

<!-- If this PR adds or modifies an alembic migration, complete this checklist. -->

If this PR includes a database migration, the migration must be tested in CI and the rollback
procedure must be documented.

- [ ] This PR does **not** include a database migration *(skip the rest of this section)*
- [ ] `alembic check` passes (no ORM↔migration drift)
- [ ] Fresh-DB drift check passes (`bash scripts/check-alembic-fresh-drift.sh`)
- [ ] `downgrade()` is implemented, or a `NotImplementedError` is raised with a comment
      explaining why the migration is irreversible
- [ ] If touching `lineage_*` or `audit_log` tables: confirm value-changes capture still works

## Frontend / UI

<!-- If this PR touches HTML / JS / CSS, complete this checklist. -->

- [ ] This PR does **not** touch `frontend/` *(skip the rest of this section)*
- [ ] Relevant e2e walkthrough(s) under `docs/e2e-walkthroughs/` replayed
- [ ] Alpine `x-data` / HTMX swaps verified in a real browser
- [ ] Bootstrap modal / dropdown toggles verified (see `feedback_bootstrap_modal_x_show.md` if applicable)
