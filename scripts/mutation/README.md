# Mutation testing

Mutation testing measures whether the test suite actually *detects*
behavioural changes, not just whether it executes the code. mutmut
rewrites each target function into many small "mutants" (flip a `>` to
`>=`, drop a `+ 1`, swap a string) and runs the tests against each. A
mutant that the tests still pass on **survived** — a blind spot. One the
tests catch is **killed**.

This project mutates the two business-logic packages,
`pointlessql/pql/` and `pointlessql/services/`, where the logic-at-a-seam
is unit-tested. Routes / models / config are integration-shell code and
are covered end-to-end instead.

## Why a wrapper (and not bare `mutmut`)

mutmut 3.x's generated trampoline reads `os.environ['MUTANT_UNDER_TEST']`
with a hard index. Some tests swap `os.environ` wholesale, which makes
that index raise `KeyError` and aborts the run.
[`run_mutmut.py`](run_mutmut.py) patches the trampoline template to read
the variable defensively **before** mutmut builds its mutant CST, then
forwards every argument to the real mutmut CLI. Always go through it.

There is no committed mutmut dependency on purpose — it is opt-in via
`uv run --with`. Pin the version so runs are reproducible:

```bash
MUTMUT="uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py"
```

## Full run

```bash
$MUTMUT run          # ~2 h on 12 cores; ~53k mutants over pql + services
$MUTMUT results      # summary table; killed / survived / no-test / timeout
$MUTMUT show <id>    # the diff for one mutant
```

mutmut copies the repo to `mutants/`, runs the full unit suite **once**
to map each mutant to its covering tests (this stats pass dominates the
wall-clock floor — ~3 min for the suite), then forks workers. Mutants
with no covering test exit instantly (free); only covered ones cost time.

`mutants/` and `mutmut-stats.json` are git-ignored — they are the
working copy, never committed.

## Scoped re-verify loop

After adding tests for one module, re-check just that module without a
full 2 h run:

```bash
rm -f mutants/mutmut-stats.json                       # force fresh stats
$MUTMUT run "pointlessql.services.alert_feeds.*"      # stats (~3 min) + only this module's mutants
```

The glob matches mangled mutant names (`<module>.<func>__mutmut_<n>`).
Budget ~4–5 min per iteration — the suite-wide stats pass is the floor;
the module's own mutants run on top.

## Reading per-module results

Each mutated source file has a sidecar `mutants/<path>.py.meta` whose
`exit_code_by_key` maps every mutant to an exit code:

| exit code | meaning            |
|----------:|--------------------|
| 0         | **survived** (blind spot — add a test) |
| 1 / 3     | killed (tests caught it) |
| 33        | no covering test (mutant was never exercised) |
| 36 / 255  | timeout (treated as killed) |

## Known-equivalent mutants

Some survivors are *equivalent* — the mutation cannot change observable
behaviour, so no test can kill them (`typing.cast` no-ops, cosmetic
error-string content, timing arithmetic). These are recorded in
`equivalent.txt` with a one-line reason each, the same allow-list shape
as `scripts/check-file-size-budget.sh`, so the CI gate does not flag them.

## Setup gotchas (already handled in the harness)

- **`also_copy`**: anything loaded by relative path (e.g.
  `frontend/templates`) must be copied into `mutants/` — see
  `also_copy` in `setup.cfg`.
- **Source-scanning meta-tests** (`test_no_bare_http_exception.py`,
  `test_no_lossy_broad_except.py`) and **docstring/signature
  introspection tests** are excluded via `pytest_add_cli_args` — they
  would see the mutated tree / stripped trampoline wrappers and fail
  spuriously.
- **Module-global state leaks**: mutmut runs pytest many times in one
  process, so a test that mutates a module global without cleanup fails
  on the 2nd run. Fix the leak at the source (never mask it); reproduce
  with two `pytest.main([...])` calls in one process.
