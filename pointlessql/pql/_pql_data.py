# pyright: reportUnusedClass=false, reportPrivateUsage=false
# This module's whole job is to compose the per-concern private
# ``_*Mixin`` classes back into one ``_DataOpsMixin`` — importing those
# package-private mixins across module boundaries is intentional here.
"""Composite data-ops mixin for the :class:`PQL` façade.

Item C split the 678-LOC monolith into per-concern
mixin files (one per public method cluster).  This module keeps
the :class:`_DataOpsMixin` name + import path stable by composing
the new mixins back into a single class — :mod:`pointlessql.pql.pql`
inherits from ``_DataOpsMixin`` exactly as before, downstream tests
that import ``_DataOpsMixin`` keep finding it here, and adding a
new public method is now a focused edit in one per-concern file
instead of a touch on the monolith.

Per-concern modules:

* :mod:`._pql_read`          — :class:`_ReadMixin`
* :mod:`._pql_sql`           — :class:`_SqlMixin`
* :mod:`._pql_write`         — :class:`_WriteMixin`
* :mod:`._pql_vector`        — :class:`_VectorMixin`
* :mod:`._pql_update_delete` — :class:`_UpdateDeleteMixin`
* :mod:`._pql_aggregate`     — :class:`_AggregateMixin`
* :mod:`._pql_autoload`      — :class:`_AutoloadMixin`
* :mod:`._pql_list`          — :class:`_ListMixin`
* :mod:`._pql_widgets`       — :class:`_WidgetsMixin`
"""

from __future__ import annotations

from pointlessql.pql._pql_aggregate import _AggregateMixin
from pointlessql.pql._pql_autoload import _AutoloadMixin
from pointlessql.pql._pql_list import _ListMixin
from pointlessql.pql._pql_read import _ReadMixin
from pointlessql.pql._pql_sql import _SqlMixin
from pointlessql.pql._pql_update_delete import _UpdateDeleteMixin
from pointlessql.pql._pql_vector import _VectorMixin
from pointlessql.pql._pql_widgets import _WidgetsMixin
from pointlessql.pql._pql_write import _WriteMixin


class _DataOpsMixin(
    _ReadMixin,
    _WriteMixin,
    _SqlMixin,
    _VectorMixin,
    _UpdateDeleteMixin,
    _AggregateMixin,
    _AutoloadMixin,
    _ListMixin,
    _WidgetsMixin,
):
    """Read, write, merge, SQL, vector, list, update, delete, aggregate, autoload, widgets.

    Composite mixin — every public method comes from one of the nine
    per-concern mixins listed above.  See the module docstring for the
    cluster mapping.  Adding a new PQL data-op = edit the matching
    per-concern file (or create a new one + add to this MRO) instead
    of growing one 700-LOC class.
    """
