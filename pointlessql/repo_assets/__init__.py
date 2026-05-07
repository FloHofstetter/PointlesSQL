"""Yaml loaders for repo-canonical dashboards + saved queries.

Phase 51.3 — sister modules to :mod:`pointlessql.data_products`
and :mod:`pointlessql.conventions`.  A workspace-repo can ship
``pointlessql.yaml`` blocks declaring dashboards and saved
queries; the loader UPSERTs them as cache rows with
``source='repo:<slug>'`` so the admin UI can render them as
read-only.

Yaml shape (all keys optional):

.. code-block:: yaml

    dashboards:
      - slug: weekly-orders
        title: Weekly orders volume
        description: Volume of orders per ISO week.
        notebook_path: dashboards/weekly_orders.py

    saved_queries:
      - slug: top-customers-q1-2026
        title: Top customers (Q1 2026)
        description: Top 50 customers by order_total in Q1 2026.
        sql_text: |
          SELECT customer_id, SUM(order_total) AS total
          FROM main.sales_gold.orders
          WHERE ordered_at >= '2026-01-01'
          GROUP BY 1
          ORDER BY 2 DESC
          LIMIT 50
        is_shared: true

The same yaml file can carry both top-level keys (and the
data-product / conventions blocks the other loaders pick up).

Anti-goals for this v1 surface:

* No DB-side enforcement that ``source`` rows can't be edited
  through the legacy admin pages.  Repo-loaded rows are
  refreshed every time the loader runs; manual edits get
  overwritten on the next ``reload``.  A future sub-sprint can
  harden this with a UI-side guard if the convention proves too
  loose.
* No deletion of rows whose yaml entry was removed.  Operators
  who want repo deletion to propagate use the admin-side
  ``DELETE`` after removing the yaml entry.
"""

from __future__ import annotations

from pointlessql.repo_assets._loader import (
    load_dashboards_for_workspace,
    load_dashboards_from_yaml,
    load_saved_queries_for_workspace,
    load_saved_queries_from_yaml,
)

__all__ = [
    "load_dashboards_for_workspace",
    "load_dashboards_from_yaml",
    "load_saved_queries_for_workspace",
    "load_saved_queries_from_yaml",
]
