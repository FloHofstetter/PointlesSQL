"""Module-level path anchors shared across every settings sub-module.

Both constants are captured at import time so a later ``Settings()``
instantiation inside a papermill worker (which may have issued
``os.chdir`` mid-process) resolves to the same absolute path the
scheduler's startup-time settings did.

Attributes:
    STARTUP_CWD: ``Path.cwd()`` snapshotted at module import — before
        any papermill ``os.chdir`` can run. Relative-path defaults in
        :class:`JupyterSettings` and :class:`WorkspaceReposSettings`
        anchor against this so the path the validator hands back is
        CWD-independent.
    PROJECT_ROOT: Repository root derived from this module's location
        on disk. ``_settings/_paths.py`` sits at
        ``<repo>/pointlessql/config/_settings/_paths.py``; four
        ``parent`` hops therefore land on ``<repo>/``. Used by
        :class:`DatabaseSettings`, :class:`DataProductsSettings` and
        :class:`WorkspaceReposSettings` to default their on-disk
        anchors stably regardless of which CWD the server was started
        from.

Both names are intentionally public-within-package (no leading
underscore) so cross-module imports inside ``_settings/`` don't trip
``pyright reportPrivateUsage``.  The enclosing package
(``pointlessql.config._settings``) is itself underscore-private, so
external callers cannot reach these symbols through the public facade.
"""

from __future__ import annotations

from pathlib import Path

STARTUP_CWD = Path.cwd()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
