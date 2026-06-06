"""A domain-agnostic node-kind registry for canvas consumers.

The dataframe layer registers blocks whose behaviour is "compile to a
DuckDB CTE + infer an output schema"; the scheduler registers task kinds
whose behaviour is "execute, with a config schema and no data schema".
Both share the *structure* — a typed catalog of node kinds keyed by
``type_name``, each declaring its pin shape — but differ entirely in what
hangs off each kind.  Rather than bake one domain's behaviour into the
registry (the old ``BlockSpec`` welded ``compile_fn``/``infer_fn`` in,
which left the scheduler unable to reuse it), this registry stores an
opaque ``behavior`` payload each consumer owns and casts back to its own
type at its own dispatch sites.

Each consumer instantiates its *own* :class:`NodeKindRegistry` — they are
never a shared module global — so a dataframe ``compile_fn`` and a
scheduler config-schema never end up in the same bag.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeKindSpec:
    """One node kind's structural contract, independent of any domain.

    Attributes:
        type_name: Registry key matching ``CanvasNode.block_type``.
        input_pins: Ordered ``(pin_name, pin_kind)`` pairs.  ``pin_kind``
            is an opaque string — ``"table"`` for dataframe rowsets,
            ``"control"`` for scheduler dependency wires — interpreted by
            the owning consumer, never by the kernel.
        output_pins: Same shape; a terminal sink declares none.
        behavior: The consumer-specific payload (a dataframe
            compile/infer pair, a scheduler config schema, …).  Opaque
            here; cast back to the concrete type at the consumer's
            dispatch site.
    """

    type_name: str
    input_pins: tuple[tuple[str, str], ...]
    output_pins: tuple[tuple[str, str], ...]
    behavior: object


class NodeKindRegistry:
    """A per-consumer catalog of :class:`NodeKindSpec` keyed by type name."""

    def __init__(self) -> None:
        self._kinds: dict[str, NodeKindSpec] = {}

    def register(self, spec: NodeKindSpec) -> None:
        """Add (or replace) a node kind in this registry.

        Args:
            spec: The kind to register, keyed by its ``type_name``.
        """
        self._kinds[spec.type_name] = spec

    def get(self, type_name: str) -> NodeKindSpec | None:
        """Return the kind registered under *type_name*, or ``None``."""
        return self._kinds.get(type_name)

    def __contains__(self, type_name: object) -> bool:
        """Report whether *type_name* is a registered kind."""
        return type_name in self._kinds

    def types(self) -> tuple[str, ...]:
        """Return every registered type name, in registration order."""
        return tuple(self._kinds)


__all__ = ["NodeKindRegistry", "NodeKindSpec"]
