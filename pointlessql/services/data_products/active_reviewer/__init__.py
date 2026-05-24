"""split per concern.

The pre-Phase-110 layout collapsed every concern into one ~760 LOC
``active_reviewer.py`` module.  Phase 110.8 split it along the natural
axes:

* :mod:`._verdict`  — ``ReviewVerdict`` dataclass +
  ``parse_review_result``.
* :mod:`._prompt`   — ``build_prompt`` daily-briefing renderer.
* :mod:`._config`   — ``upsert_config`` + ``iter_opted_in_dp_ids``.
* :mod:`._writers`  — comment / endorsement / agent-review writers
  and the ``call_llm`` round-trip stubbable by tests.
* :mod:`._run`      — ``run_reviewer_for_dp`` end-to-end orchestration.

The public surface (six callables + dataclass) matches the pre-split
import path so ``services.data_products.__init__`` and the two test
modules need no edits.
"""

from __future__ import annotations

from pointlessql.services.data_products.active_reviewer._config import (
    iter_opted_in_dp_ids,
    upsert_config,
)
from pointlessql.services.data_products.active_reviewer._prompt import build_prompt
from pointlessql.services.data_products.active_reviewer._run import run_reviewer_for_dp
from pointlessql.services.data_products.active_reviewer._verdict import (
    ReviewVerdict,
    parse_review_result,
)

__all__ = [
    "ReviewVerdict",
    "build_prompt",
    "iter_opted_in_dp_ids",
    "parse_review_result",
    "run_reviewer_for_dp",
    "upsert_config",
]
