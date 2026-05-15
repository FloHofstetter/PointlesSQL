"""Social-graph models (Phase 76.2+).

Houses the user-to-user follow + per-user profile + badge tables
that drive ``/users/{id}`` pages and per-user activity feeds.
Kept under a dedicated ``social`` sub-package so the catalog
namespace stays focused on data-product metadata.
"""

from __future__ import annotations

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

__all__ = [
    "BADGE_KEYS",
    "ENTITY_KINDS",
    "DataProductTopic",
    "SocialStar",
    "SocialTarget",
    "Topic",
    "UserBadge",
    "UserFollow",
    "UserProfile",
    "UserTopicFollow",
]
