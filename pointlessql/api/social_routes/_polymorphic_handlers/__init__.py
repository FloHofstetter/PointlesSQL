"""Kind-agnostic social-write handlers — split-package facade.

The original ``_polymorphic_handlers.py`` was 2231 LOC across nine
behavioural axes (comments, endorsements, follows, reactions, stars,
READMEs, reviews) plus a shared helpers / serialisers block.  Phase
89.1 split each axis into its own sub-module; this ``__init__``
re-exports every public handler name the 7 sibling route modules
(``comments.py``, ``endorsements.py``, ``follows.py``, ``reviews.py``,
``reactions.py``, ``stars.py``, ``readme.py``) import from this
package, so the existing call sites keep working unchanged.

Locked decisions from the original module-level docstring continue
to apply — see the ``_shared`` module for the file-private
constants and the per-axis modules for the actual route bodies.
"""

from __future__ import annotations

from pointlessql.api.social_routes._polymorphic_handlers._comments import (
    delete_polymorphic_comment,
    list_polymorphic_comments,
    post_polymorphic_comment,
)
from pointlessql.api.social_routes._polymorphic_handlers._endorsements import (
    apply_polymorphic_endorsement,
    list_polymorphic_endorsements,
    remove_polymorphic_endorsement,
)
from pointlessql.api.social_routes._polymorphic_handlers._followers import (
    follow_polymorphic_entity,
    get_polymorphic_followers_count,
    list_polymorphic_followers,
    unfollow_polymorphic_entity,
)
from pointlessql.api.social_routes._polymorphic_handlers._reactions_comment import (
    apply_polymorphic_comment_reaction,
    list_polymorphic_comment_reactions,
    remove_polymorphic_comment_reaction,
)
from pointlessql.api.social_routes._polymorphic_handlers._reactions_entity import (
    apply_polymorphic_reaction,
    list_polymorphic_reactions,
    remove_polymorphic_reaction,
)
from pointlessql.api.social_routes._polymorphic_handlers._reactions_review import (
    apply_polymorphic_review_reaction,
    list_polymorphic_review_reactions,
    remove_polymorphic_review_reaction,
)
from pointlessql.api.social_routes._polymorphic_handlers._readme import (
    get_polymorphic_readme,
    put_polymorphic_readme,
)
from pointlessql.api.social_routes._polymorphic_handlers._reviews import (
    delete_polymorphic_review,
    list_polymorphic_reviews,
    upsert_polymorphic_review,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    ALLOWED_CATEGORIES,
    ALLOWED_EMOJI,
)
from pointlessql.api.social_routes._polymorphic_handlers._stars import (
    get_polymorphic_star,
    list_user_stars,
    star_polymorphic_entity,
    unstar_polymorphic_entity,
)

__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_EMOJI",
    "apply_polymorphic_comment_reaction",
    "apply_polymorphic_endorsement",
    "apply_polymorphic_reaction",
    "delete_polymorphic_comment",
    "delete_polymorphic_review",
    "follow_polymorphic_entity",
    "get_polymorphic_followers_count",
    "get_polymorphic_readme",
    "get_polymorphic_star",
    "list_polymorphic_comment_reactions",
    "list_polymorphic_comments",
    "list_polymorphic_endorsements",
    "list_polymorphic_followers",
    "list_polymorphic_reactions",
    "list_polymorphic_review_reactions",
    "list_polymorphic_reviews",
    "list_user_stars",
    "post_polymorphic_comment",
    "put_polymorphic_readme",
    "apply_polymorphic_review_reaction",
    "remove_polymorphic_comment_reaction",
    "remove_polymorphic_endorsement",
    "remove_polymorphic_reaction",
    "remove_polymorphic_review_reaction",
    "star_polymorphic_entity",
    "unfollow_polymorphic_entity",
    "unstar_polymorphic_entity",
    "upsert_polymorphic_review",
]
