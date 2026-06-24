"""Hypothesis profiles for the SQL-parser verification suite.

Three named profiles trade coverage for wall-clock: ``ci`` (lean, the PR
gate), ``dev`` (the local default), and ``nightly`` (deep).  Examples are
pure parsing — no I/O — but per-example deadlines are disabled anyway so a
cold sqlglot import on the first example never trips a spurious deadline.
The active profile is chosen by the ``HYPOTHESIS_PROFILE`` env var (default
``dev``).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

_SUPPRESS = [HealthCheck.too_slow]

settings.register_profile("dev", max_examples=50, deadline=None, suppress_health_check=_SUPPRESS)
settings.register_profile(
    "ci",
    max_examples=30,
    deadline=None,
    derandomize=True,
    print_blob=True,
    suppress_health_check=_SUPPRESS,
)
settings.register_profile(
    "nightly",
    max_examples=500,
    deadline=None,
    suppress_health_check=_SUPPRESS,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
