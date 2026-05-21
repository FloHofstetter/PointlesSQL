"""Native-editor notebook persistence: outputs + per-cell run history.

The notebook ORM grew from 5 tables in Phase 77.6 to 18 across Phases
77–105 as the editor accumulated cell-identity reconciliation, AI
proposals, revisions, replays, branches, share + permission lattices,
and real-time co-edit.  This package keeps every table addressable
under the historical ``pointlessql.models.notebook`` import path while
splitting the implementation per phase so future maintenance can read
each cluster in isolation.
"""

from __future__ import annotations

from pointlessql.models.notebook._authorship import NotebookCellAuthorship
from pointlessql.models.notebook._branch import NotebookBranchBinding
from pointlessql.models.notebook._coedit import NotebookCrdtState
from pointlessql.models.notebook._core import (
    Notebook,
    NotebookCellIdentity,
    NotebookCellRun,
    NotebookCellRunSource,
    NotebookJobLink,
    NotebookOutput,
)
from pointlessql.models.notebook._proposals import (
    NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES,
    NotebookCellSequenceProposal,
)
from pointlessql.models.notebook._provenance import NotebookCellProvenance
from pointlessql.models.notebook._replays import NotebookReplay
from pointlessql.models.notebook._revisions import (
    NotebookRevision,
    NotebookRevisionFact,
)
from pointlessql.models.notebook._share import (
    NotebookPermission,
    NotebookShare,
    NotebookWidget,
)
from pointlessql.models.notebook._tags import NotebookTag

__all__ = [
    "NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES",
    "Notebook",
    "NotebookBranchBinding",
    "NotebookCellAuthorship",
    "NotebookCellIdentity",
    "NotebookCellProvenance",
    "NotebookCellRun",
    "NotebookCellRunSource",
    "NotebookCellSequenceProposal",
    "NotebookCrdtState",
    "NotebookJobLink",
    "NotebookOutput",
    "NotebookPermission",
    "NotebookReplay",
    "NotebookRevision",
    "NotebookRevisionFact",
    "NotebookShare",
    "NotebookTag",
    "NotebookWidget",
]
