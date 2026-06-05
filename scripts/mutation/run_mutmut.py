#!/usr/bin/env python
"""Run mutmut against PointlesSQL with the trampoline KeyError patch applied.

mutmut 3.x rewrites every target function into a *trampoline* that reads
``os.environ['MUTANT_UNDER_TEST']`` with a hard index. Several tests in
the suite swap ``os.environ`` wholesale (e.g.
``monkeypatch.setattr(os, "environ", {})``), which turns that index into a
``KeyError`` and aborts the whole run. This wrapper rewrites the trampoline
template to read the variable defensively *before* ``mutmut.file_mutation``
imports it — that module binds ``trampoline_impl`` by value and parses it
into a CST at import time, so the patch has to land first. Every written
mutant then carries the patched trampoline.

All command-line arguments are forwarded verbatim to the mutmut CLI, so
this is a drop-in replacement for ``mutmut``::

    uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py run
    uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py results
    uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py run "<glob>"

See ``scripts/mutation/README.md`` for the full workflow, including the
scoped re-verify loop and how to read per-module ``.meta`` exit codes.
"""

from __future__ import annotations

_HARD_INDEX = "os.environ['MUTANT_UNDER_TEST']"
_SAFE_GET = "os.environ.get('MUTANT_UNDER_TEST', '')"


def _patch_trampoline_template() -> None:
    """Rewrite the trampoline's env lookup to a defensive ``.get`` form.

    Must run before ``mutmut.file_mutation`` is imported: that module does
    ``from mutmut.trampoline_templates import trampoline_impl`` and builds
    its CST from the value at import time, so a later patch is ignored.

    Raises:
        SystemExit: if the upstream template no longer contains the hard
            index this patch targets — fail loudly so a mutmut upgrade
            can't silently reintroduce the ``KeyError``.
    """
    import mutmut.trampoline_templates as templates

    if _HARD_INDEX not in templates.trampoline_impl:
        raise SystemExit(
            "mutmut trampoline template changed shape: "
            f"{_HARD_INDEX!r} not found. Re-derive the patch in "
            "scripts/mutation/run_mutmut.py against the installed mutmut."
        )
    templates.trampoline_impl = templates.trampoline_impl.replace(_HARD_INDEX, _SAFE_GET)


def main() -> None:
    """Apply the trampoline patch, then hand off to mutmut's Click CLI."""
    _patch_trampoline_template()

    from mutmut.__main__ import cli

    cli()


if __name__ == "__main__":
    main()
