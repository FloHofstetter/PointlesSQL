# pyright: reportUnusedClass=false
"""Governance mixin for the :class:`PQL` façade — branch / rollback / training-context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pointlessql.config import get_settings
from pointlessql.pql._branch import (
    create_branch_schema,
    discard_branch_schema,
    preview_promote_conflicts,
    promote_branch_schema,
)
from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._rollback import RollbackResult, rollback_table
from pointlessql.types import OpName


class _GovernanceMixin(_PQLBase):
    """Training-context, rollback, and the four branch lifecycle methods."""

    def training_context(
        self,
        *,
        framework: str = "auto",
        op_name: OpName = OpName.TRAIN_MODEL,
        params: Mapping[str, Any] | None = None,
        source_table_fqn: str | None = None,
        model_fqn: str | None = None,
    ) -> Any:
        """Wrap a training block so MLflow autolog fires + audit row lands.

        agents call::

            with pql.training_context(framework="sklearn"):
                model.fit(X, y)

        The wrapper enables ``mlflow.autolog()`` for the requested
        framework, opens an MLflow run (or nests under an outer one),
        captures ``run.data.params + .metrics`` at exit, and stores
        the JSON-encoded snapshot on the audit operation row's
        ``training_params_json`` column. Best-effort: works without
        MLflow installed (audit row still lands, snapshot is empty).

        / pass both ``source_table_fqn``
        and ``model_fqn`` to anchor a single training-source edge in
        ``lineage_row_edges`` so the model-detail Lineage DAG paints
        the upstream training source.  Either alone or both unset →
        no edge.

        Args:
            framework: Hint for ``mlflow.autolog`` flavor; defaults to
                ``"auto"``.
            op_name: Audit-row label; defaults to ``"train_model"``.
            params: Optional initial params dict merged into the
                operation row.
            source_table_fqn: Optional UC FQN of the gold/training
                table the model was fit on.
            model_fqn: Optional UC FQN of the registered model the
                training will produce.  Drives the audit-row's
                ``target_table`` and (with ``source_table_fqn``) the
                training-source lineage edge.

        Returns:
            A context manager yielding a
            :class:`~pointlessql.services.agent_runs.training_context.TrainingRecorder`.
        """
        from pointlessql.db import get_session_factory
        from pointlessql.services.agent_runs.training_context import (
            training_context as _training_context,
        )

        factory = get_session_factory() if self._current_run_id else None
        return _training_context(
            factory,
            agent_run_id=self._current_run_id,
            framework=framework,
            op_name=op_name,
            params=dict(params) if params is not None else None,
            source_table_fqn=source_table_fqn,
            model_fqn=model_fqn,
        )

    def rollback(
        self,
        target: str,
        *,
        before_run: str,
        op_ordinal: int | None = None,
        allow_force: bool = False,
    ) -> RollbackResult:
        """Undo *before_run*'s write to *target* via Delta restore.

        Looks up the targeted operation by ``(before_run, target)``
        in ``agent_run_operations``, recovers its
        ``delta_version_before``, and atomically restores the Delta
        table to that version.  Rollback IS an operation: a fresh
        ``agent_run_operations`` row is emitted with
        ``op_name='rollback'`` so the audit trail records the undo
        alongside the original change.

        The four refusal modes are evaluated *before* the Delta
        state is mutated.  Pass ``op_ordinal`` to disambiguate runs
        that wrote *target* more than once; pass
        ``allow_force=True`` to suppress the staleness check when
        intervening writes by other runs would otherwise be
        silently overwritten.

        Args:
            target: UC ``"catalog.schema.table"`` reference.  Must
                already exist in soyuz-catalog.
            before_run: ``agent_runs.id`` of the run whose write
                to *target* should be undone.
            op_ordinal: Explicit ordinal of the op to rollback when
                the run touched *target* more than once.  ``None``
                works when exactly one op matches.
            allow_force: When ``True``, bypass the staleness check.
                Defaults to ``False`` so a casual click cannot
                silently overwrite intervening writes from other
                runs.

        Returns:
            A :class:`RollbackResult` with ``version_before``,
            ``version_after``, the historical
            ``target_version_restored``, and the
            ``restored_file_count`` reported by the deltalake
            metrics dict.
        """
        return rollback_table(
            client=self._client,
            target=target,
            before_run=before_run,
            unreachable_msg=self._unreachable_msg(),
            op_ordinal=op_ordinal,
            allow_force=allow_force,
            agent_run_id=self._current_run_id,
        )

    def branch(
        self,
        source_schema: str,
        branch_name: str,
        *,
        strategy: Literal["auto", "symlink", "deep_copy"] = "auto",
    ) -> str:
        """Create a Delta branch of *source_schema* under *branch_name*.

         entry point.  Drops a fresh UC schema named
        ``catalog.branch_name`` (catalog is inherited from
        *source_schema*) whose Delta tables either symlink (local
        FS) or deep-copy (cloud, opt-in) the source's parquet files,
        then stamps the schema with ``pointlessql.branch.*`` tag
        metadata so subsequent ``pql.branch_discard`` /
        ``pql.branch_promote`` calls can find it.

        Writes against the branch (``pql.write_table``,
        ``pql.merge``, etc.) land in the branch's storage prefix and
        do not touch the parent — this is the isolation guarantee.

        Args:
            source_schema: Two-part ``catalog.schema`` of the parent.
            branch_name: Plain branch schema name (no dots).
            strategy: ``"auto"`` (recommended), ``"symlink"``, or
                ``"deep_copy"``.  ``"auto"`` resolves to symlink on
                local FS and to either deep-copy or
                :class:`BranchCloudUnsupportedError` on cloud
                storage, depending on
                ``settings.branch.cloud_strategy``.

        Returns:
            The branch's two-part FQN ``catalog.branch_name``.
        """
        return create_branch_schema(
            client=self._client,
            source_schema_fqn=source_schema,
            branch_name=branch_name,
            settings=get_settings(),
            strategy=strategy,
            agent_run_id=self._current_run_id,
        )

    def branch_promote(self, branch_schema: str) -> dict[str, str]:
        """Promote a branch to be the new parent via UC pointer-swap.

         entry point.  Refuses promotion when the parent
        moved between branch creation and now (raises
        :class:`BranchPromotionConflictError`); recovery is to discard
        and re-branch.  v1 is pointer-swap-only — the parent is
        renamed to ``{parent}_pre_promote_<ts>`` (backup), the branch
        is renamed to the parent's old name, and tags are updated.

        Permission gate: caller is responsible for enforcing
        admin / supervisor scope before invoking.  The route handler
        in 16.5.5 wraps this with :func:`require_admin`.

        Args:
            branch_schema: Two-part ``catalog.branch_name``.

        Returns:
            ``{"new_parent": ..., "backup": ...}``.
        """
        return promote_branch_schema(
            client=self._client,
            branch_schema_fqn=branch_schema,
            settings=get_settings(),
            agent_run_id=self._current_run_id,
        )

    def branch_promote_preview(self, branch_schema: str) -> dict[str, Any]:
        """Dry-run conflict-detection for a planned promotion.

        Returns ``{ok: bool, conflicts: list[...]}`` without mutating
        any UC state.  The Control-Room UI renders this directly so
        a reviewer sees the conflict-report before clicking promote.

        Args:
            branch_schema: Two-part ``catalog.branch_name``.

        Returns:
            Conflict report dict (see :func:`preview_promote_conflicts`).
        """
        return preview_promote_conflicts(
            client=self._client,
            branch_schema_fqn=branch_schema,
        )

    def branch_discard(self, branch_schema: str) -> None:
        """Permanently remove a Delta branch and its UC namespace.

         entry point.  Idempotent for already-discarded
        branches (no-op + warning log).  Refuses to discard a
        promoted branch — promotion is final.  Cleans up the local-
        FS storage tree without touching the source parquets that
        symlinks point at.

        Args:
            branch_schema: Two-part ``catalog.branch_name`` of the
                branch to remove.
        """
        discard_branch_schema(
            client=self._client,
            branch_schema_fqn=branch_schema,
            settings=get_settings(),
            agent_run_id=self._current_run_id,
        )
