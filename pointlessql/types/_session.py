"""Structural protocol for ``sessionmaker``-shaped session factories.

Service helpers that only need ``with factory() as session: ...``
accept :class:`SessionFactory` instead of the concrete
``sessionmaker[Session]`` so a caller can pass the app-state factory,
a test double, or any compatible callable interchangeably.  This is
the one canonical definition; modules used to each declare a private
``_SessionFactory`` copy of the same shape.
"""

from __future__ import annotations

from typing import Any, Protocol


class SessionFactory(Protocol):
    """Callable that returns a new SQLAlchemy session.

    Calling the factory yields a session usable as a context manager
    (``with factory() as session: ...``) — the ``sessionmaker``
    ``__call__`` contract, captured structurally so test doubles and
    the app-state factory satisfy it without inheriting from
    ``sessionmaker``.

    ``__call__`` is intentionally typed ``-> Any`` rather than
    ``-> Session``: the service layer uses these sessions with
    defensive ``hasattr`` guards, ``CursorResult.rowcount`` access, and
    nullable-in-practice columns that a strict ``Session`` return type
    would flag under pyright.  ``Any`` keeps the one shared contract
    behaviour-identical to the per-module copies it replaces.
    """

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...
