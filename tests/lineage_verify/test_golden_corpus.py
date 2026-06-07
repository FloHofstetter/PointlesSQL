"""Golden-corpus regression: deterministic lineage matches committed snapshots.

Each curated pipeline runs real PQL primitives with fixed inputs and asserts
its recorded lineage equals a committed JSON snapshot.  Re-generate the
snapshots after an intended change with ``LINEAGE_CORPUS_UPDATE=1 pytest
tests/lineage_verify/test_golden_corpus.py``; the diff is then reviewable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.lineage_verify._corpus import CORPUS, serialize_facts

_CORPUS_DIR = Path(__file__).parent / "corpus"


@pytest.mark.lineage_verify
@pytest.mark.parametrize("name", sorted(CORPUS))
def test_golden_corpus(name: str) -> None:
    actual = serialize_facts(CORPUS[name]())
    snapshot = _CORPUS_DIR / f"{name}.json"

    if os.environ.get("LINEAGE_CORPUS_UPDATE"):
        _CORPUS_DIR.mkdir(exist_ok=True)
        snapshot.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    assert snapshot.exists(), (
        f"missing golden snapshot {snapshot.name}; regenerate with LINEAGE_CORPUS_UPDATE=1"
    )
    expected = json.loads(snapshot.read_text(encoding="utf-8"))
    assert actual == expected
