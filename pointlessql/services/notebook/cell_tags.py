"""Curated cell-tag vocabulary.

The notebook ``.py`` marker grammar already round-trips arbitrary
``tags=["..."]`` lists losslessly through
:mod:`pointlessql.services.notebook._doc`. This adds a hybrid
UI picker: a curated dropdown of light-categorisation tags plus a
``Custom…`` escape for free-text entries.

This module exposes the curated list as a Python constant that
:mod:`pointlessql.api.notebooks_routes.pages` passes into the editor
template; the front-end factory iterates the constant verbatim.  The
backend does NOT enforce the curated list — saving a cell with
``tags=["literally-anything"]`` continues to work, which keeps the
``.py`` IDE-agnostic.

The ``"parameters"`` tag stays out of the curated list because it
already has a dedicated dropdown menu item in the cell-header (papermill
parameters semantics).
"""

from __future__ import annotations

CURATED_CELL_TAGS: tuple[str, ...] = (
    "etl",
    "draft",
    "prod",
    "wip",
    "verified",
    "broken",
)
"""Default cell-tag vocabulary surfaced in the editor's tag picker.

Picked for early adopters' lifecycle / status categorisation.
Drift watch: once the long-tail of custom tags grows past a handful
of stable values, a Phase-96 curation pass folds the popular ones in
here and demotes anything that turned out to be one-off.
"""


__all__: list[str] = ["CURATED_CELL_TAGS"]
