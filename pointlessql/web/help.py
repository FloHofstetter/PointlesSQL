"""Contextual help-popover registry (Phase 23).

Single source of truth for the copy that powers the small
``bi-info-circle`` icons across the web UI.  Templates call
``help('<slug>')`` via the Jinja global registered in
:mod:`pointlessql.api.main` and render through the
``frontend/templates/_macros/help_icon.html`` macro.

Slug schema is ``<page>.<topic>`` (lowercase-kebab inside each
component); each entry is a :class:`HelpEntry` carrying

* ``title`` — the popover header (≤ 60 chars)
* ``body`` — 1-3 sentences explaining *what* and *why* (≤ 280 chars,
  the popover renders narrow by default)
* ``learn_more`` — optional mkdocs path (``/concepts/agent-runs/``)
  prefixed at render time with the public docs base URL.

Tests in ``tests/test_help_registry.py`` enforce the length
constraints and resolve every slug declared in templates back to
this registry, so a missing or mistyped slug surfaces in CI rather
than as an empty popover at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpEntry:
    """One help-popover entry.

    Attributes:
        title: Popover header.  Kept short (≤ 60 chars) so the
            Bootstrap-rendered title row does not wrap awkwardly.
        body: 1-3 sentences explaining the concept.  Plain text +
            the Bootstrap default sanitizer's allow-list (``<a>``,
            ``<br>``, ``<strong>``, ``<em>``).  Capped at 280 chars
            because the default popover width is ~270 px.
        learn_more: Optional mkdocs path.  Must start with ``/``
            and resolve under ``https://flohofstetter.github.io/
            PointlesSQL`` at render time.  ``None`` means the
            popover renders without a "Learn more →" link.
    """

    title: str
    body: str
    learn_more: str | None = None


HELP: dict[str, HelpEntry] = {
    "runs.what-is-a-run": HelpEntry(
        title="What is an agent run?",
        body=(
            "A supervised pipeline execution triggered by an "
            "external runtime (Hermes, OpenShell, cron). Every "
            "operation, tool call, and write is captured in the "
            "audit trail."
        ),
        learn_more="/concepts/agent-runs/",
    ),
    "runs.what-is-an-operation": HelpEntry(
        title="What is an operation?",
        body=(
            "Operations are the unit of supervision inside a run: "
            "one autoload, write, merge, query, or rollback per "
            "row. Errors stop the run; warnings (e.g. lineage-emit "
            "hiccups) annotate the row but keep status=ok."
        ),
        learn_more="/concepts/operations/",
    ),
    "models.what-is-promotion": HelpEntry(
        title="What is model promotion?",
        body=(
            "Promotion moves a model version from challenger to "
            "champion — the version inference APIs serve. Only "
            "READY versions can be promoted, and every promotion "
            "is logged with promoter, reason, and timestamp."
        ),
        learn_more="/concepts/model-promotion/",
    ),
    "branches.what-is-a-delta-branch": HelpEntry(
        title="What is a Delta branch?",
        body=(
            "A zero-copy snapshot of one or more Delta tables, "
            "created so an agent run can write in isolation. "
            "Branches are either promoted (changes merged back to "
            "parent) or discarded — never partially applied."
        ),
        learn_more="/concepts/delta-branching/",
    ),
    "lineage.what-is-lineage": HelpEntry(
        title="What is lineage?",
        body=(
            "The data-provenance graph: which tables, columns, "
            "and rows fed which downstream artefacts. PointlesSQL "
            "captures table-, column-, row-, and value-level "
            "lineage on every PQL write — readable forwards "
            "(impact analysis) and backwards (root-cause)."
        ),
        learn_more="/concepts/lineage/",
    ),
}


def get_help(slug: str) -> HelpEntry:
    """Resolve a help slug to its registry entry.

    Unknown slugs propagate :class:`KeyError` from the underlying
    dict lookup — a typo in a template fails loudly in tests and
    dev rather than silently rendering an empty popover.

    Args:
        slug: The slug used in templates, e.g. ``runs.what-is-a-run``.

    Returns:
        The :class:`HelpEntry` registered for ``slug``.
    """
    return HELP[slug]
