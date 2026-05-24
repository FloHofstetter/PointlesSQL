"""Validation registry for social ``(kind, ref)`` URL pairs.

extracted from
``_kind_dispatch.parse_ref()``'s 13-way if/elif chain.  Each
:class:`RefKind` carries a short error message and a validator
that returns True iff *ref* is well-formed for the kind.  The
:func:`parse_ref` dispatcher in :mod:`_kind_dispatch` looks up
the matching :class:`RefKind` and raises a uniform
:class:`BadRequestError` with the kind's message when validation
fails.

Pattern mirrors
:class:`pointlessql.services.social.citations.CitationKind` —
each entity kind documents its own ref shape inline, and adding a
new kind is a single :func:`register_ref_kind` call rather than a
new elif branch.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RefKind:
    """Validation spec for one ``(kind, ref)`` pair.

    Attributes:
        key: The kind discriminator from the URL path
            (``"table"``, ``"branch"``, etc.).
        validate: Predicate that returns ``True`` iff *ref* is
            well-formed for this kind.
        message: Human-readable error message used when
            :attr:`validate` returns ``False``.  Stored on the
            spec so the dispatcher can raise a uniform
            :class:`BadRequestError` without hand-rolling per-kind
            text.
    """

    key: str
    validate: Callable[[str], bool]
    message: str


def _is_three_part_fqn(ref: str) -> bool:
    """Return True iff *ref* is a three-part dotted FQN with no empty parts."""
    parts = ref.split(".", 2)
    return len(parts) == 3 and all(parts)


def _is_two_part_fqn(ref: str) -> bool:
    """Return True iff *ref* is a two-part dotted FQN with no empty parts."""
    parts = ref.split(".", 1)
    return len(parts) == 2 and all(parts)


def _is_uuid36(ref: str) -> bool:
    """Return True iff *ref* is a 36-character UUID (4 hyphens)."""
    return len(ref) == 36 and ref.count("-") == 4


def _is_bare_identifier(ref: str) -> bool:
    """Return True iff *ref* is a non-empty identifier without ``.`` or ``/``."""
    return bool(ref) and "." not in ref and "/" not in ref


def _is_slug(ref: str) -> bool:
    """Return True iff *ref* is a non-empty slug (no ``/``)."""
    return bool(ref) and "/" not in ref


def _is_branch_fqn(ref: str) -> bool:
    """Return True iff *ref* looks like a branch FQN (carries ``__branch_`` + ``.``)."""
    return "__branch_" in ref and "." in ref


def _is_notebook_cell_ref(ref: str) -> bool:
    """Return True iff *ref* is ``{notebook_uuid}:{cell_uuid}`` (two UUIDs)."""
    notebook_uuid, sep, cell_uuid = ref.partition(":")
    if not sep:
        return False
    return _is_uuid36(notebook_uuid) and _is_uuid36(cell_uuid)


def _is_issue_id(ref: str) -> bool:
    """Return True iff *ref* is a non-empty digit string (issue id)."""
    return bool(ref) and ref.isdigit()


_REF_KINDS: list[RefKind] = [
    RefKind(
        key="table",
        validate=_is_three_part_fqn,
        message="kind='table' ref must be 'catalog.schema.table'.",
    ),
    RefKind(
        key="branch",
        validate=_is_branch_fqn,
        message=(
            "kind='branch' ref must be a branch FQN "
            "('catalog.schema__branch_xxx')."
        ),
    ),
    RefKind(
        key="model",
        validate=_is_three_part_fqn,
        message="kind='model' ref must be 'catalog.schema.name'.",
    ),
    RefKind(
        key="run",
        validate=_is_uuid36,
        message="kind='run' ref must be a 36-char UUID.",
    ),
    RefKind(
        key="issue",
        validate=_is_issue_id,
        message="kind='issue' ref must be a numeric issue id.",
    ),
    RefKind(
        key="schema",
        validate=_is_two_part_fqn,
        message="kind='schema' ref must be 'catalog.schema'.",
    ),
    RefKind(
        key="catalog",
        validate=_is_bare_identifier,
        message="kind='catalog' ref must be a bare identifier.",
    ),
    RefKind(
        key="notebook",
        validate=_is_uuid36,
        message="kind='notebook' ref must be a 36-char UUID.",
    ),
    RefKind(
        key="saved_query",
        validate=_is_slug,
        message="kind='saved_query' ref must be a slug.",
    ),
    RefKind(
        key="workspace",
        validate=lambda r: _is_bare_identifier(r),
        message="kind='workspace' ref must be a slug.",
    ),
    RefKind(
        key="notebook_cell",
        validate=_is_notebook_cell_ref,
        message=(
            "kind='notebook_cell' ref must be "
            "'{notebook_uuid}:{cell_uuid}' (two 36-char UUIDs)."
        ),
    ),
]


def find_ref_kind(kind: str) -> RefKind | None:
    """Return the :class:`RefKind` registered for *kind*, or ``None``.

    Args:
        kind: The kind discriminator from the URL path.

    Returns:
        The matching spec, or ``None`` when no kind by that name is
        registered.
    """
    return next((spec for spec in _REF_KINDS if spec.key == kind), None)


def register_ref_kind(spec: RefKind) -> None:
    """Append a new :class:`RefKind` to the registry.

    Args:
        spec: The new kind specification.

    Raises:
        ValueError: When a kind by the same key is already
            registered.  This makes accidental double-registration
            a loud error instead of a silent override.
    """
    if find_ref_kind(spec.key) is not None:
        msg = f"RefKind {spec.key!r} is already registered"
        raise ValueError(msg)
    _REF_KINDS.append(spec)


__all__ = ["RefKind", "find_ref_kind", "register_ref_kind"]
