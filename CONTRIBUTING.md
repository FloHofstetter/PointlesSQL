# Contributing to PointlesSQL

Thank you for your interest in PointlesSQL — a per-cell auditable
lakehouse for agent-driven data engineering, EU-AI-Act-native.
Contributions of all sizes are welcome.

## Before you start

By contributing, you agree that your contribution will be licensed
under the same terms as the project (Apache License, Version 2.0).
A bot will ask you to sign the Individual CLA on your first pull
request — this is a one-time step that lets the project relicense
in the future if needed (e.g. for a future commercial offering
built on the same core).

## Reporting issues

- **Bug reports** and **feature requests** go through GitHub
  Issues — pick the right template from the *New Issue* picker.
- **Security vulnerabilities** must NOT be filed as public issues.
  See [`SECURITY.md`](SECURITY.md) for the responsible-disclosure
  path.

## Development environment

PointlesSQL is a Python 3.14 project managed with
[`uv`](https://docs.astral.sh/uv/). The dependency graph requires
a separately running [soyuz-catalog](https://github.com/FloHofstetter/soyuz-catalog)
process (PointlesSQL talks to it over HTTP).

```bash
# 1. clone and sync
git clone git@github.com:FloHofstetter/PointlesSQL.git
cd PointlesSQL
uv sync

# 2. start soyuz-catalog in another terminal
cd ~/git/soyuz-catalog && uv run soyuz-catalog

# 3. start PointlesSQL
uv run pointlessql       # serves http://127.0.0.1:8000
```

If you need to iterate on `soyuz-catalog` itself,
`bash scripts/use-editable-soyuz.sh` swaps the pinned git tag for
an editable path dependency on the sibling checkout.

## Local gates

The same gates that CI runs. Run all of them before opening a PR.

```bash
uv run pytest -m 'not integration'         # unit tests
uv run pytest -m integration               # integration (needs live soyuz)
uv run ruff check . && uv run ruff format --check .
uv run pyright                             # type-check
uv run pydoclint pointlessql               # docstring lint
bash scripts/check-file-size-budget.sh     # file-size budget
bash scripts/check-pyright-budget.sh       # pyright warning budget
bash scripts/check-alembic-fresh-drift.sh  # alembic ORM↔migration drift
```

`uv run pre-commit install` arms the hook so most of these run on
every commit.

## Branch and commit conventions

- **Branch**: any descriptive name (`fix/lineage-rejects-tab`,
  `feat/audit-cockpit-search`, …).
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
  format — `feat(scope): …`, `fix(scope): …`, `docs(scope): …`,
  `chore(scope): …`. Scope is the subsystem touched
  (`ui`, `pql`, `audit`, `alembic`, `docs`, `ci`, …).

## Pull request process

1. Open a draft PR early — feedback is cheaper before the change
   is finished.
2. Fill in the PR template. Tick every gate that applies, untick
   anything that doesn't.
3. Replay the relevant end-to-end walkthroughs under
   [`docs/e2e-walkthroughs/`](docs/e2e-walkthroughs/) when your
   change touches HTML, JS, or CSS — type-checkers cannot catch
   x-data quoting bugs.
4. One reviewer (the project owner today) signs off. CI must be
   green.
5. Update [`CHANGELOG.md`](CHANGELOG.md) and [`ROADMAP.md`](ROADMAP.md)
   in the same PR when the change closes or extends a sprint.

## Fixing bugs at the source

PointlesSQL, `soyuz-catalog` (and its generated
`soyuz-catalog-client`), and the `hermes-plugin-pointlessql`
bridge are all first-party repositories. When a bug surfaces in a
dependency we own, fix it there instead of working around it
locally — that keeps both codebases clean and avoids stale
workaround code outliving the bug.

## Adding a documentation page

The `docs/` tree is governed by
[`docs/internal/doc-site-ia.md`](docs/internal/doc-site-ia.md) —
the IA contract that decides which subdirectory a new page
belongs in (`getting-started/`, `concepts/`, `guides/`,
`e2e-walkthroughs/`, `admin/`, `integrations/`, `reference/`,
`development/`, `decisions/`, `research/`, or the maintainer-only
`internal/`).

After picking the subdirectory and adding the file:

1. Add a `nav:` entry in [`mkdocs.yml`](mkdocs.yml) under the
   matching group — OR add it to `exclude_docs:` if the file is a
   maintainer-only artifact under `docs/internal/`.
2. Run `uv run --group docs --no-default-groups mkdocs build`
   locally to surface broken links.
3. The pre-commit `doc-orphans` hook
   ([`scripts/check-doc-orphans.sh`](scripts/check-doc-orphans.sh))
   fails any commit that leaves a new `.md` file orphan. The
   baseline allowance is 18 e2e-walkthroughs that are tracked for
   theme-grouped renaming in a later wave.

## Code of conduct

Be kind. Disagree with code, not with people. The project follows
the spirit of the Contributor Covenant; the formal text will be
added before the public visibility flip.
