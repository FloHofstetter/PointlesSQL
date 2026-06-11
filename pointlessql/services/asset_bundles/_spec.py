"""Pydantic ``BundleSpec`` — strict YAML-or-dict bundle input.

``extra=forbid`` everywhere so typos in user-authored YAML surface as
validation errors rather than silently-ignored fields.  Field names
mirror the live resources closely enough that the spec round-trips
against :mod:`pointlessql.services.asset_bundles._exporter`.
"""

from __future__ import annotations

from typing import Any

import yaml
from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pointlessql.models.bi_dashboards import BI_WIDGET_KINDS
from pointlessql.models.pipelines import (
    PIPELINE_DATASET_KINDS,
    PIPELINE_EXPECTATION_ACTIONS,
)
from pointlessql.services.bi_dashboards import PARAM_TYPES
from pointlessql.services.scheduler import (
    NOTIFY_ON_CHOICES,
    RUN_IF_CHOICES,
    TRIGGER_KINDS,
)

EVENT_CRON_SENTINEL = "@event"
"""``Job.cron_expr`` value written for event-triggered jobs."""


class BundleInfo(BaseModel):
    """Bundle header: a name plus an optional description."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("bundle.name cannot be blank")
        return cleaned


class JobTriggerSpec(BaseModel):
    """Non-default trigger of a job (file arrival / table update)."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    path: str | None = None
    table: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value not in TRIGGER_KINDS:
            raise ValueError(f"trigger.kind must be one of {list(TRIGGER_KINDS)}, got {value!r}")
        return value


class JobTaskSpec(BaseModel):
    """One node of a job DAG; ``name`` is the reconciliation identity."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    max_retries: int = Field(default=0, ge=0)
    retry_backoff_seconds: int = Field(default=0, ge=0)
    run_if: str = "all_success"
    for_each: list[Any] | None = None

    @field_validator("name", "kind")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("task name / kind cannot be blank")
        return cleaned

    @field_validator("run_if")
    @classmethod
    def _check_run_if(cls, value: str) -> str:
        if value not in RUN_IF_CHOICES:
            raise ValueError(f"run_if must be one of {list(RUN_IF_CHOICES)}, got {value!r}")
        return value


class JobSpec(BaseModel):
    """One scheduler job; ``name`` is the reconciliation identity."""

    model_config = ConfigDict(extra="forbid")

    name: str
    cron: str | None = None
    kind: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    paused: bool = False
    max_parallel_runs: int = Field(default=1, ge=1)
    trigger: JobTriggerSpec | None = None
    notify_on: list[str] = Field(default_factory=list)
    run_as: str | None = None
    tasks: list[JobTaskSpec] = Field(default_factory=list[JobTaskSpec])

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("job name cannot be blank")
        return cleaned

    @field_validator("notify_on")
    @classmethod
    def _check_notify_on(cls, value: list[str]) -> list[str]:
        bad = [entry for entry in value if entry not in NOTIFY_ON_CHOICES]
        if bad:
            raise ValueError(f"notify_on must be a subset of {list(NOTIFY_ON_CHOICES)}, got {bad}")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> JobSpec:
        kind = self.trigger_kind()
        if kind == "cron":
            if not self.cron:
                raise ValueError(f"job {self.name!r}: cron is required for cron-triggered jobs")
            if not croniter.is_valid(self.cron):
                raise ValueError(f"job {self.name!r}: invalid cron expression {self.cron!r}")
        elif kind == "file_arrival":
            if self.trigger is None or not str(self.trigger.path or "").strip():
                raise ValueError(f"job {self.name!r}: file_arrival trigger needs a path glob")
        elif kind == "table_update" and (
            self.trigger is None or not str(self.trigger.table or "").strip()
        ):
            raise ValueError(
                f"job {self.name!r}: table_update trigger needs a table (catalog.schema.table)"
            )
        if not self.tasks and not self.kind:
            raise ValueError(f"job {self.name!r}: kind is required when no tasks are declared")
        names: set[str] = set()
        for task in self.tasks:
            if task.name in names:
                raise ValueError(f"job {self.name!r}: duplicate task name {task.name!r}")
            names.add(task.name)
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in names:
                    raise ValueError(
                        f"job {self.name!r}: task {task.name!r} depends on unknown task {dep!r}"
                    )
        return self

    def trigger_kind(self) -> str:
        """Return the effective trigger kind (``cron`` when unset)."""
        return self.trigger.kind if self.trigger is not None else "cron"

    def effective_cron(self) -> str:
        """Return the ``cron_expr`` to store (sentinel for event jobs)."""
        if self.trigger_kind() == "cron":
            return str(self.cron)
        return EVENT_CRON_SENTINEL

    def trigger_config(self) -> dict[str, str]:
        """Return the ``trigger_config`` payload for the trigger kind."""
        if self.trigger is None or self.trigger.kind == "cron":
            return {}
        if self.trigger.kind == "file_arrival":
            return {"path": str(self.trigger.path)}
        return {"table": str(self.trigger.table)}

    def effective_kind(self) -> str:
        """Return the ``Job.kind`` to store (placeholder for DAG jobs)."""
        if self.kind is not None:
            return self.kind
        return "python"


class ExpectationSpec(BaseModel):
    """One data-quality expectation on a pipeline dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str
    constraint: str
    action: str = "warn"

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: str) -> str:
        if value not in PIPELINE_EXPECTATION_ACTIONS:
            raise ValueError(
                f"expectation action must be one of {list(PIPELINE_EXPECTATION_ACTIONS)}, "
                f"got {value!r}"
            )
        return value


class DatasetSpec(BaseModel):
    """One pipeline dataset (target FQN + kind + SELECT)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    sql: str
    expectations: list[ExpectationSpec] = Field(default_factory=list[ExpectationSpec])

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value not in PIPELINE_DATASET_KINDS:
            raise ValueError(
                f"dataset kind must be one of {list(PIPELINE_DATASET_KINDS)}, got {value!r}"
            )
        return value


class PipelineSpec(BaseModel):
    """One declarative pipeline; ``slug`` (or ``title``) is the identity."""

    model_config = ConfigDict(extra="forbid")

    slug: str | None = None
    title: str
    description: str | None = None
    datasets: list[DatasetSpec] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("pipeline title cannot be blank")
        return cleaned

    def identity(self) -> str:
        """Return the reconciliation identity (slug when set, else title)."""
        return self.slug or self.title


class DashboardParamSpec(BaseModel):
    """One dashboard-level parameter declaration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    type: str = "string"
    default: Any = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in PARAM_TYPES:
            raise ValueError(f"param type must be one of {list(PARAM_TYPES)}, got {value!r}")
        return value


class WidgetSpec(BaseModel):
    """One dashboard widget; ``(kind, title)`` is the matching key."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    title: str | None = None
    sql: str | None = None
    markdown: str | None = None
    chart_spec: dict[str, Any] | None = None
    position: dict[str, Any] | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value not in BI_WIDGET_KINDS:
            raise ValueError(f"widget kind must be one of {list(BI_WIDGET_KINDS)}, got {value!r}")
        return value

    @model_validator(mode="after")
    def _check_source(self) -> WidgetSpec:
        if self.kind == "markdown":
            if not self.markdown:
                raise ValueError("markdown widgets need a markdown body")
        elif not (self.sql or "").strip():
            raise ValueError(f"{self.kind} widgets need inline sql")
        return self

    def matching_key(self) -> tuple[str, str]:
        """Return the ``(kind, title)`` pair used for widget matching."""
        return (self.kind, self.title or "")


class DashboardSpec(BaseModel):
    """One BI dashboard; ``slug`` is the reconciliation identity."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    description: str | None = None
    params: list[DashboardParamSpec] = Field(default_factory=list[DashboardParamSpec])
    widgets: list[WidgetSpec] = Field(default_factory=list[WidgetSpec])

    @field_validator("slug", "title")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("dashboard slug / title cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def _check_widget_keys(self) -> DashboardSpec:
        seen: set[tuple[str, str]] = set()
        for widget in self.widgets:
            key = widget.matching_key()
            if key in seen:
                raise ValueError(
                    f"dashboard {self.slug!r}: duplicate widget (kind, title) pair {key!r} — "
                    "widget matching needs unique pairs"
                )
            seen.add(key)
        return self


class BundleSpec(BaseModel):
    """Top-level bundle: header plus declared jobs / pipelines / dashboards."""

    model_config = ConfigDict(extra="forbid")

    bundle: BundleInfo
    jobs: list[JobSpec] = Field(default_factory=list[JobSpec])
    pipelines: list[PipelineSpec] = Field(default_factory=list[PipelineSpec])
    dashboards: list[DashboardSpec] = Field(default_factory=list[DashboardSpec])

    @model_validator(mode="after")
    def _check_identities(self) -> BundleSpec:
        for label, identities in (
            ("job name", [j.name for j in self.jobs]),
            ("pipeline identity", [p.identity() for p in self.pipelines]),
            ("dashboard slug", [d.slug for d in self.dashboards]),
        ):
            seen: set[str] = set()
            for identity in identities:
                if identity in seen:
                    raise ValueError(f"duplicate {label} {identity!r}")
                seen.add(identity)
        return self


def parse_bundle(source: str | dict[str, Any]) -> BundleSpec:
    """Return a validated :class:`BundleSpec`.

    Args:
        source: YAML text or a pre-decoded dict.

    Returns:
        The bundle spec parsed and validated from *source*.

    Raises:
        ValueError: On YAML parse error or pydantic validation error.
    """
    if isinstance(source, dict):
        return BundleSpec.model_validate(source)
    try:
        decoded = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise ValueError(f"yaml parse error: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("bundle must be a YAML mapping")
    return BundleSpec.model_validate(decoded)
