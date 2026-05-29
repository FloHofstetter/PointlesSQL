"""ORM models for catalog metadata: queries, dashboards, recents, autoload, data products, sync.

Five flat sibling modules consolidated into one
``pointlessql.models.catalog`` package whose ``__init__.py``
re-exports the 11 public symbols.

Layout:

* ``_metadata``       — :class:`Dashboard`, :class:`QueryHistory`,
                        :class:`QueryHistoryTable`, :class:`RateLimitEvent`,
                        :class:`SavedQuery`, :class:`TableStats`.
* ``_recents``        — :class:`RecentTable` (per-user catalog-tree
                        recently-visited bookmarks).
* ``_autoload``       — :class:`AutoloadCheckpoint` (autoload
                        per-target-table progress checkpoint).
* ``_data_products``  — :class:`DataProduct`,
                        :class:`DataProductContractEvent`
                        + ``CONTRACT_EVENT_OUTCOMES`` constant.
* ``_data_product_comments`` — :class:`DataProductComment`
                        (threaded discussion rows).
* ``_data_product_reviews``  — :class:`DataProductReview`
                        (one-per-user star + body row).
* ``_data_product_trending`` — :class:`DataProductTrending`
                        (cached trending rank rows).
* ``_data_product_endorsement`` — :class:`DataProductEndorsement`
                        (typed manual endorsements).
* ``_data_product_candidate`` — :class:`DataProductPromotionCandidate`
                        (promote-to-DP candidate cache).
* ``_data_product_yaml_draft`` — :class:`DataProductYamlDraft`
                        (draft yaml file tracking).
* ``_sync``           — :class:`SyncRun` (foreign-catalog sync run
                        history).
"""

from __future__ import annotations

from pointlessql.models.catalog._autoload import AutoloadCheckpoint
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    ACTIVE_REVIEWER_PROVIDERS,
    ACTIVE_REVIEWER_RUNNERS,
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_product_candidate import (
    CANDIDATE_STATUSES,
    DataProductPromotionCandidate,
)
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_cooccurrence import (
    DataProductCooccurrence,
)
from pointlessql.models.catalog._data_product_endorsement import (
    ENDORSEMENT_TYPES,
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_passport import (
    PASSPORT_TRIGGERS,
    DataProductPassport,
)
from pointlessql.models.catalog._data_product_proposal import (
    PROPOSAL_STATUSES,
    DataProductSchemaProposal,
)
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_product_trending import DataProductTrending
from pointlessql.models.catalog._data_product_yaml_draft import (
    YAML_DRAFT_SOURCE_KINDS,
    DataProductYamlDraft,
)
from pointlessql.models.catalog._data_products import (
    CONTRACT_EVENT_OUTCOMES,
    DataProduct,
    DataProductContractEvent,
    DataProductStatistics,
)
from pointlessql.models.catalog._domains import (
    DOMAIN_ARCHETYPES,
    DOMAIN_MEMBER_ROLES,
    DP_TRANSFORMATION_KINDS,
    DataProductTransformation,
    Domain,
    DomainMember,
)
from pointlessql.models.catalog._glossary import (
    GlossaryTerm,
    GlossaryTermColumn,
)
from pointlessql.models.catalog._governance import (
    CLASSIFICATIONS,
    ENCRYPTION_CLASSES,
    FORGET_STATUSES,
    MASKING_STRATEGIES,
    DataProductColumnClassification,
    DataProductForgetRequest,
    DataProductPolicy,
    WorkspaceGovernancePolicy,
)
from pointlessql.models.catalog._mesh import (
    MeshEntity,
    MeshEntityBinding,
)
from pointlessql.models.catalog._metadata import (
    Dashboard,
    QueryHistory,
    QueryHistoryTable,
    RateLimitEvent,
    SavedQuery,
    TableStats,
)
from pointlessql.models.catalog._ports import (
    INPUT_PORT_KINDS,
    OUTPUT_PORT_KINDS,
    DataProductInputPort,
    DataProductOutputPort,
)
from pointlessql.models.catalog._recents import RecentTable
from pointlessql.models.catalog._semantic import (
    DataProductSemanticConcept,
)
from pointlessql.models.catalog._slo import (
    MEASURABLE_SLO_KINDS,
    SLO_COMPARATORS,
    SLO_KINDS,
    DataProductSLO,
)
from pointlessql.models.catalog._sync import SyncRun

__all__ = [
    "ACTIVE_REVIEWER_PROVIDERS",
    "ACTIVE_REVIEWER_RUNNERS",
    "CANDIDATE_STATUSES",
    "CLASSIFICATIONS",
    "CONTRACT_EVENT_OUTCOMES",
    "DOMAIN_ARCHETYPES",
    "DOMAIN_MEMBER_ROLES",
    "DP_TRANSFORMATION_KINDS",
    "ENCRYPTION_CLASSES",
    "ENDORSEMENT_TYPES",
    "FORGET_STATUSES",
    "INPUT_PORT_KINDS",
    "MASKING_STRATEGIES",
    "MEASURABLE_SLO_KINDS",
    "OUTPUT_PORT_KINDS",
    "PASSPORT_TRIGGERS",
    "PROPOSAL_STATUSES",
    "SLO_COMPARATORS",
    "SLO_KINDS",
    "YAML_DRAFT_SOURCE_KINDS",
    "AutoloadCheckpoint",
    "Dashboard",
    "DataProduct",
    "DataProductActiveReviewerConfig",
    "DataProductColumnClassification",
    "DataProductComment",
    "DataProductCommentReaction",
    "DataProductContractEvent",
    "DataProductCooccurrence",
    "DataProductEndorsement",
    "DataProductForgetRequest",
    "DataProductInputPort",
    "DataProductOutputPort",
    "DataProductPassport",
    "DataProductPolicy",
    "DataProductPromotionCandidate",
    "DataProductReview",
    "DataProductSLO",
    "DataProductSchemaProposal",
    "DataProductSemanticConcept",
    "DataProductStatistics",
    "DataProductTransformation",
    "DataProductTrending",
    "DataProductYamlDraft",
    "Domain",
    "DomainMember",
    "GlossaryTerm",
    "GlossaryTermColumn",
    "MeshEntity",
    "MeshEntityBinding",
    "QueryHistory",
    "QueryHistoryTable",
    "RateLimitEvent",
    "RecentTable",
    "SavedQuery",
    "SyncRun",
    "TableStats",
    "WorkspaceGovernancePolicy",
]
