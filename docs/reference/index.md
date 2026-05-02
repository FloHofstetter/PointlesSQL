# Reference

The full API surface of PointlesSQL — Python, REST, CLI,
configuration, events, permissions.

| Section | Audience | What's there |
|---|---|---|
| **[Python API](python/index.md)** | Notebook authors, agents | The `PQL` class (19 public methods) + selected service modules. Auto-generated from Google-style docstrings via `mkdocstrings`. |
| **[REST API](api.md)** | Plugin authors, ops | The top-30 most-used routes hand-polished (auth, runs, models, lineage, write, merge, branch, supervisor, auditor). adds the auto-generated appendix for the long tail. |
| **[CLI](cli.md)** | Operators | The `pointlessql` Typer command + the one `admin issue-auditor-key` subcommand. |
| **[Configuration](configuration.md)** | Operators, deploy engineers | Every `POINTLESSQL_*` env var grouped by `settings.py` sub-model with rationale. |
| **[CloudEvents](cloudevents.md)** | Webhook receivers, integrators | The 12 `pointlessql.<domain>.<verb>` event types with payload schemas + examples. |
| **[Permissions](permissions.md)** | Security reviewers | The trust-tier matrix (anonymous → cookie → API key → +supervisor / +auditor → admin). |

## What's hand-written vs auto-generated

| Surface | Source of truth | Drift handling |
|---|---|---|
| Python API | `pointlessql/**/*.py` docstrings | Re-rendered on every `mkdocs build` — drift impossible |
| REST API top-30 | This file (hand-curated) | Reviewed manually per sprint that adds new routes |
| CLI | `pointlessql/api/main.py` cli() block | Reviewed when the Typer surface grows (rarely — currently 2 commands) |
| Configuration | `pointlessql/settings.py` | will add a `gen_config_docs.py` script that re-emits this from `Settings.model_json_schema()` |
| CloudEvents | `pointlessql/services/audit_stream/` + grep | Reviewed manually; the 12 types haven't changed since |
| Permissions | `pointlessql/api/dependencies.py` + plugin `tools/__init__.py` | Reviewed when scope flags or family gates change |

## Out of scope

- **OpenAPI spec download** — the FastAPI app exposes it at
 `/openapi.json`; the docs site doesn't redistribute it.
- **`X-Trace-Id` reference** — PointlesSQL does not yet carry
 request tracing across services. candidate.
