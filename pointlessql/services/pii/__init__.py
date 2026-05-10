"""PII redaction, hashing, masking, and tag resolution.

Three flat sibling modules (pii_redactor 191 + pii_resolver 175
+ pii_mask 74 = 440 LOC) consolidated into one
``pointlessql.services.pii`` package whose ``__init__.py``
re-exports the seven public symbols.

Layout:

* ``_redactor`` — ``is_pii_by_name``, ``hash_value``,
  ``redact_value``, and the install-global secret accessor
  (``get_or_create_pii_hash_secret``) used by the canonical
  hashing path.
* ``_resolver`` — async UC-tag-resolution cache
  (``resolve_many``) plus invalidation helpers.
* ``_mask``     — surface masker (``mask_value``) used at the
  API boundary to render PII as readable replacement strings.
"""

from __future__ import annotations

from pointlessql.services.pii._mask import mask_value
from pointlessql.services.pii._redactor import (
    get_or_create_pii_hash_secret,
    hash_value,
    is_pii_by_name,
    redact_value,
)
from pointlessql.services.pii._resolver import (
    invalidate,
    invalidate_all,
    resolve_many,
)

__all__ = [
    "get_or_create_pii_hash_secret",
    "hash_value",
    "invalidate",
    "invalidate_all",
    "is_pii_by_name",
    "mask_value",
    "redact_value",
    "resolve_many",
]
