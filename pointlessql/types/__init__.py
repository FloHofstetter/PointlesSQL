"""Project-wide type contracts: enums, identifiers, error codes, FQNs.

This package consolidates the small "shape" modules that used to
sit as five flat siblings at ``pointlessql/`` root.  The public
surface is identical — every symbol is re-exported here so
consumers can keep importing from one place
(``from pointlessql.types import OpName, TableFqn, ErrorCode``).

Layout (private modules, do not import directly):

* ``_enums``        — :class:`StrEnum` classes for status / kind
                      columns (RunStatus, OpName, ReadKind, ...).
* ``_identifiers``  — :class:`NewType` aliases for primary IDs
                      (RunId, OpId, WorkspaceId, ...).
* ``_user_types``   — :class:`UserInfo` TypedDict for the
                      auth-middleware payload.
* ``_table_fqn``    — :class:`TableFqn` validated three-part
                      identifier.
* ``_error_codes``  — :class:`ErrorCode` enum referenced by
                      every domain exception.
* ``_session``      — :class:`SessionFactory` structural protocol
                      for ``sessionmaker``-shaped callables.
"""

from __future__ import annotations

from pointlessql.types._enums import (
    AuditSinkType,
    BranchAction,
    EventOutcome,
    OpName,
    QueryStatus,
    ReadKind,
    ReviewKind,
    ReviewSeverity,
    RunStatus,
)
from pointlessql.types._error_codes import ErrorCode
from pointlessql.types._identifiers import (
    OpId,
    QueryHistoryId,
    RunId,
    WorkspaceId,
)
from pointlessql.types._session import SessionFactory
from pointlessql.types._table_fqn import TableFqn
from pointlessql.types._user_types import UserInfo

__all__ = [
    "AuditSinkType",
    "BranchAction",
    "ErrorCode",
    "EventOutcome",
    "OpId",
    "OpName",
    "QueryHistoryId",
    "QueryStatus",
    "ReadKind",
    "ReviewKind",
    "ReviewSeverity",
    "RunId",
    "RunStatus",
    "SessionFactory",
    "TableFqn",
    "UserInfo",
    "WorkspaceId",
]
