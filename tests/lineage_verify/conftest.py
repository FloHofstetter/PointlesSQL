"""Hypothesis profiles for the lineage-verification suite.

Three named profiles trade coverage for wall-clock: ``ci`` (lean, the PR
gate), ``dev`` (the local default), and ``nightly`` (deep).  Each example
runs real Delta + DB I/O, so per-example deadlines are disabled and the
slow-data health check is suppressed.  The active profile is chosen by the
``HYPOTHESIS_PROFILE`` env var (default ``dev``).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

_SUPPRESS = [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]

settings.register_profile("dev", max_examples=25, deadline=None, suppress_health_check=_SUPPRESS)
settings.register_profile(
    "ci",
    max_examples=15,
    deadline=None,
    derandomize=True,
    print_blob=True,
    suppress_health_check=_SUPPRESS,
)
settings.register_profile(
    "nightly",
    max_examples=300,
    deadline=None,
    suppress_health_check=_SUPPRESS,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
