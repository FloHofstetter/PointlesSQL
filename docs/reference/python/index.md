# Python API

Reference docs for everything you can `from pointlessql import …`
or call from a notebook / script.

The Python surface is split into three audiences:

1. **[The `PQL` class](pql.md)** — the primary public API. Every
 read / write / merge / branch / rollback you do as a notebook
 author or an agent goes through this class. 19 public
 methods.
2. **[Service modules](services.md)** — internals you can call
 from an admin script or a custom Hermes plugin. Reference,
 not entry-point. Most users never touch these.
3. **Models / settings** — SQLAlchemy ORM rows + pydantic-
 settings sub-models. See
 [`pointlessql/models/`](https://github.com/FloHofstetter/PointlesSQL/tree/main/pointlessql/models)
 and [`pointlessql/settings.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/settings.py)
 directly. The
 [Configuration reference](../configuration.md) is the
 prose mapping over `settings.py`.

## What's auto-generated

Pages under this section render **directly from the Python
docstrings** via `mkdocstrings`. When a method or service
gets a new `Args:` / `Returns:` / `Raises:` block, the docs
update on the next `mkdocs build` — no manual edits needed.

The docstring style is **Google** (enforced in `pre-commit` by
`pydoclint`). See [`CLAUDE.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
for the convention rule.

## What's hand-written

The [REST API reference](../api.md) is hand-written for the
top-30 most-used routes (auth, runs, models, lineage, write,
merge, branch, supervisor, auditor) and gets a 
auto-gen pass for the remaining ~180. The [CLI
reference](../cli.md) is hand-written too — it's only two
commands.
