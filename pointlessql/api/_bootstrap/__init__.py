"""Internal bootstrap helpers split out of ``api/main.py``.

Private package — nothing here is part of the public API.  Each
module isolates one concern that used to inflate ``main.py`` past
1000 LOC; ``main.py`` imports them at startup time only.

Layout:

* ``_loops`` — the seven background-task coroutines (audit
  retention, external-write scan, data-product freshness, CDF
  tail, lineage pruner, workspace-repo sync, branch cleanup) the
  lifespan kicks off as long-running tasks.
"""
