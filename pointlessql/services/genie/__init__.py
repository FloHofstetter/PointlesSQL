"""Genie spaces — curated natural-language data rooms.

Package layout (split from one module at the size budget):

* ``_crud``   — space / trusted-asset / message persistence.
* ``_engine`` — prompt-context building, LLM SQL generation, and
  validation of the generated SQL against the curated table list.
"""

from __future__ import annotations

from pointlessql.services.genie._crud import (
    add_trusted_asset,
    append_message,
    create_space,
    delete_space,
    delete_trusted_asset,
    get_message,
    get_space,
    list_messages,
    list_spaces,
    list_trusted_assets,
    promote_message,
    set_feedback,
    space_metric_views,
    space_tables,
    update_space,
)
from pointlessql.services.genie._engine import (
    CONTEXT_CHAR_CAP,
    GENIE_SYSTEM_PROMPT,
    MAX_TRUSTED_EXAMPLES,
    GenieLLMNotConfiguredError,
    build_context,
    extract_sql,
    generate_sql,
    validate_generated_sql,
)

__all__ = [
    "CONTEXT_CHAR_CAP",
    "GENIE_SYSTEM_PROMPT",
    "MAX_TRUSTED_EXAMPLES",
    "GenieLLMNotConfiguredError",
    "add_trusted_asset",
    "append_message",
    "build_context",
    "create_space",
    "delete_space",
    "delete_trusted_asset",
    "extract_sql",
    "generate_sql",
    "get_message",
    "get_space",
    "list_messages",
    "list_spaces",
    "list_trusted_assets",
    "promote_message",
    "set_feedback",
    "space_metric_views",
    "space_tables",
    "update_space",
    "validate_generated_sql",
]
