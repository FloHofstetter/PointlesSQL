"""Constants + the ``MergeStrategy`` type alias for the merge primitive."""

from __future__ import annotations

from typing import Literal

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"

MergeStrategy = Literal["upsert", "scd2"]

SCD2_VALID_FROM = "_valid_from"
SCD2_VALID_TO = "_valid_to"
SCD2_IS_CURRENT = "_is_current"
