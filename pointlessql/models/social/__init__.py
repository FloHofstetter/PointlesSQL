"""Social-graph models (Phase 76.2+).

Houses the user-to-user follow + per-user profile + badge tables
that drive ``/users/{id}`` pages and per-user activity feeds.
Kept under a dedicated ``social`` sub-package so the catalog
namespace stays focused on data-product metadata.
"""

from __future__ import annotations

from pointlessql.models.social._issue import (
    ISSUE_CLOSED_REASONS,
    ISSUE_STATES,
    Issue,
)
from pointlessql.models.social._issue_label import IssueLabel
from pointlessql.models.social._issue_milestone import IssueMilestone
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_star import SocialStar
from pointlessql.models.social._social_target import (
    ENTITY_KINDS,
    SocialTarget,
)
from pointlessql.models.social._topic import (
    DataProductTopic,
    Topic,
    UserTopicFollow,
)
from pointlessql.models.social._user_badge import (
    BADGE_KEYS,
    UserBadge,
)
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.models.social._user_profile import UserProfile
from pointlessql.models.social._workspace_pin import WorkspacePinnedEntity

__all__ = [
    "BADGE_KEYS",
    "ENTITY_KINDS",
    "ISSUE_CLOSED_REASONS",
    "ISSUE_STATES",
    "DataProductTopic",
    "Issue",
    "IssueLabel",
    "IssueMilestone",
    "SocialFollow",
    "SocialStar",
    "SocialTarget",
    "Topic",
    "UserBadge",
    "UserFollow",
    "UserProfile",
    "UserTopicFollow",
    "WorkspacePinnedEntity",
]
