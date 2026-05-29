"""Aggregate-ownership heuristic — a federated suggestion, not a rule.

An aggregate-aligned product is built from other products.  When such a
product declares its upstreams (Phase-125 ``upstream_product`` input
ports), the platform can *suggest* which business domain should own it:
the domain that owns the majority of its upstreams.  This is a
read-only hint surfaced on the Governance tab; the owner still assigns
the domain explicitly.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductInputPort,
    Domain,
)


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def suggest_domain_for_aggregate(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    workspace_id: int,
) -> dict[str, Any] | None:
    """Suggest an owning domain from a product's upstream products.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: The (aggregate) product to advise on.
        workspace_id: Workspace the products live in.

    Returns:
        ``{"suggested_domain": {...}, "rationale": str,
        "upstream_domains": [{"ref", "domain"}]}`` when a majority
        domain emerges from declared ``upstream_product`` inputs, else
        ``None`` (no upstreams declared, or none carry a domain).
    """
    with session_factory() as session:
        upstreams = list(
            session.scalars(
                select(DataProductInputPort).where(
                    DataProductInputPort.data_product_id == data_product_id,
                    DataProductInputPort.kind == "upstream_product",
                )
            ).all()
        )
        if not upstreams:
            return None

        upstream_domains: list[dict[str, Any]] = []
        domain_counter: Counter[int] = Counter()
        for port in upstreams:
            ref = (port.source_ref or "").strip()
            if "." not in ref:
                continue
            catalog, _, schema = ref.partition(".")
            product = session.scalar(
                select(DataProduct).where(
                    DataProduct.workspace_id == workspace_id,
                    DataProduct.catalog_name == catalog,
                    DataProduct.schema_name == schema,
                )
            )
            domain_dict: dict[str, Any] | None = None
            if product is not None and product.domain_id is not None:
                domain = session.get(Domain, product.domain_id)
                if domain is not None:
                    domain_counter[domain.id] += 1
                    domain_dict = {
                        "id": domain.id,
                        "slug": domain.slug,
                        "name": domain.name,
                    }
            upstream_domains.append({"ref": ref, "domain": domain_dict})

        if not domain_counter:
            return None

        top_id, top_count = domain_counter.most_common(1)[0]
        top_domain = session.get(Domain, top_id)
        if top_domain is None:
            return None
        total = sum(domain_counter.values())
        return {
            "suggested_domain": {
                "id": top_domain.id,
                "slug": top_domain.slug,
                "name": top_domain.name,
            },
            "rationale": (
                f"{top_count} of {total} upstream products with a domain belong to "
                f"{top_domain.name!r}"
            ),
            "upstream_domains": upstream_domains,
        }
