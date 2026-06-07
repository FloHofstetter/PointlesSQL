#!/usr/bin/env bash
# Print the Alembic head revision the current code defines.
#
# Used by the backup/restore tooling and the DR game-day to compare the
# code's schema version against a backup's recorded revision. Prints the
# single head revision id to stdout (empty + non-zero exit if none / on
# error), so it is safe to capture:
#
#   CODE_HEAD="$(bash scripts/check-alembic-head.sh)"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

uv run python - <<'PY'
import sys
from pathlib import Path

import pointlessql
from alembic.config import Config
from alembic.script import ScriptDirectory

cfg = Config()
cfg.set_main_option("script_location", str(Path(pointlessql.__file__).resolve().parent / "alembic"))
heads = ScriptDirectory.from_config(cfg).get_heads()
if len(heads) != 1:
    print(f"expected exactly 1 alembic head, found {len(heads)}: {heads}", file=sys.stderr)
    sys.exit(1)
print(heads[0])
PY
