"""YAML loader for ``pointlessql.yaml`` conventions overrides.

The parser is deliberately small — :func:`load_conventions` reads
a YAML file (path resolved via :class:`ConventionsSettings`),
merges shallow overrides over the Medallion :data:`DEFAULT_CONVENTIONS`,
and returns the validated :class:`ConventionsConfig`.  When no
YAML path is configured the defaults are returned as-is.

The shallow-merge semantics are intentional: if the operator
overrides ``layers`` they replace the entire list (so a partial
override doesn't accidentally leave a stale default in the
middle).  Top-level scalars like ``layer_tag_key`` are merged
field-by-field because they have no internal structure to worry
about.  The behaviour matches the principle in the Phase-13.5
ROADMAP entry: "convention is configurable, not hard-coded" but
the configuration model stays predictable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pointlessql.conventions._defaults import DEFAULT_CONVENTIONS
from pointlessql.conventions._schema import ConventionsConfig
from pointlessql.settings import Settings


def load_conventions(
    path: Path | None = None,
    *,
    settings: Settings | None = None,
) -> ConventionsConfig:
    """Load Medallion conventions, merging YAML overrides over defaults.

    Resolution order for the YAML path:

    1. The explicit ``path`` argument when given.
    2. ``settings.conventions.path`` when ``path`` is ``None``.
    3. Fall back to :data:`DEFAULT_CONVENTIONS` when neither is set.

    The returned config is the agent-facing source of truth:
    Sprint-13.7's ``pql_conventions()`` tool serialises it into the
    system prompt, the conformance check (Sprint 13.5.4) consults it
    when grading writes, and the autoload primitive
    (Sprint 13.5.3) pulls audit-column names from it.

    Args:
        path: Optional explicit path to a ``pointlessql.yaml`` file.
            When passed, takes precedence over the settings field.
        settings: Optional :class:`Settings` override.  Defaults to a
            fresh ``Settings()`` so test code can inject a custom
            ``conventions.path`` without touching the environment.

    Returns:
        ConventionsConfig: The defaults when no YAML is configured,
            otherwise the defaults shallow-merged with the YAML's
            top-level fields.

    Raises:
        FileNotFoundError: If the resolved YAML path does not exist
            on disk.  We surface the failure instead of silently
            falling back so a typo in the env var is loud.
        ValueError: If the YAML file's top-level value is not a
            mapping.  YAML syntax errors propagate from
            :mod:`yaml` and validation errors from :mod:`pydantic`
            propagate as their native exception types.
    """
    resolved_settings = settings or Settings()
    resolved_path = path or resolved_settings.conventions.path

    if resolved_path is None:
        return DEFAULT_CONVENTIONS

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"pointlessql.yaml not found at {resolved_path!s} "
            "(set POINTLESSQL_CONVENTIONS_PATH= to a valid file or "
            "leave it unset to use the Medallion defaults)"
        )

    with resolved_path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

    if raw is None:
        return DEFAULT_CONVENTIONS

    if not isinstance(raw, dict):
        raise ValueError(
            f"pointlessql.yaml at {resolved_path!s} must be a mapping at "
            f"the top level, got {type(raw).__name__}"
        )

    overrides: dict[str, Any] = {str(k): v for k, v in raw.items()}
    merged: dict[str, Any] = DEFAULT_CONVENTIONS.model_dump()
    merged.update(overrides)
    return ConventionsConfig.model_validate(merged)
