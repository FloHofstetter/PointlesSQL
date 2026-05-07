"""NewType aliases for the project's primary identifier strings.

Wrapping these IDs in distinct types lets pyright catch mixups
(passing a :class:`RunId` where a :class:`WorkspaceId` was expected)
even though every alias erases to ``str`` or ``int`` at runtime.
No runtime cost, no DB migration -- purely a contract aid at the
function-signature / service / route boundary.

The module-layer SQLAlchemy ``Mapped[...]`` types stay on plain
``str`` / ``int`` -- ORM integration with :class:`NewType` is
unspec'd and risks runtime surprises on column read/write.
"""

from __future__ import annotations

from typing import NewType

RunId = NewType("RunId", str)
"""36-char UUID string for a single agent run."""

OpId = NewType("OpId", int)
"""Auto-increment PK on ``agent_run_operations``."""

QueryHistoryId = NewType("QueryHistoryId", int)
"""Auto-increment PK on ``query_history``."""

WorkspaceId = NewType("WorkspaceId", int)
"""Auto-increment PK on ``workspaces``; resolved from middleware."""
