"""Generate the authorization-coverage matrix from the live route table.

Walks the FastAPI app's routes, extracts the authorization gate(s) attached
to each (the ``require_*`` / ``admin_uc`` dependencies, at route or router
level), and writes ``docs/internal/authz-matrix.md`` classifying every route
as one of:

* **role-gated** — carries an explicit ``require_*`` role dependency;
* **public** — on the ``PUBLIC_PREFIXES`` unauthenticated allowlist;
* **authenticated** — neither of the above, so the *global* auth middleware
  still requires a logged-in principal (any authenticated user may call it).

So "authenticated" is the safe default, not a hole. The genuinely useful
review signal is the **admin-path-without-a-role-gate** section: routes whose
path looks privileged (contains ``/admin``) yet carry no role gate — exactly
what a reviewer should double-check. Run after adding routes and commit the
regenerated matrix:

    uv run python scripts/authz_matrix_generate.py

This is an inventory generator, not a test — the parametrised matrix tests
that assert each (route, persona) -> status live separately (deferred).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Dependency callables recognised as authorization gates.  Anything whose
# name starts with ``require_`` counts; these are the extras that do not.
_EXTRA_GATE_NAMES = {"admin_uc"}


def _collect_gates(dependant: Any, seen: set[int] | None = None) -> set[str]:
    """Recursively collect gate names from a FastAPI Dependant tree.

    Args:
        dependant: A route or router ``Dependant``.
        seen: Visited-id set guarding against cyclic dependency graphs.

    Returns:
        The set of gate function names guarding this dependant.
    """
    seen = seen if seen is not None else set()
    gates: set[str] = set()
    for sub in getattr(dependant, "dependencies", []):
        call = getattr(sub, "call", None)
        name = getattr(call, "__name__", None)
        if name and (name.startswith("require_") or name in _EXTRA_GATE_NAMES):
            gates.add(name)
        if id(sub) not in seen:
            seen.add(id(sub))
            gates |= _collect_gates(sub, seen)
    return gates


def _is_public(path: str, public_prefixes: tuple[str, ...]) -> bool:
    """Whether *path* is on the unauthenticated public allowlist."""
    return any(path.startswith(prefix) for prefix in public_prefixes)


def build_rows() -> list[tuple[str, str, str, str]]:
    """Build ``(method, path, gates, status)`` rows for every API route."""
    from fastapi.routing import APIRoute

    from pointlessql.api.main import app
    from pointlessql.api.middleware import PUBLIC_PREFIXES

    rows: list[tuple[str, str, str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        gates = _collect_gates(route.dependant)
        methods = sorted(m for m in route.methods if m not in {"HEAD", "OPTIONS"})
        for method in methods:
            if gates:
                status = "role-gated"
                gate_text = ", ".join(sorted(gates))
            elif _is_public(route.path, PUBLIC_PREFIXES):
                status = "public"
                gate_text = "(public allowlist)"
            else:
                status = "authenticated"
                gate_text = "(login required, no role gate)"
            rows.append((method, route.path, gate_text, status))
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def render_markdown(rows: list[tuple[str, str, str, str]]) -> str:
    """Render the matrix rows as a Markdown document."""
    admin_no_gate = [r for r in rows if r[3] == "authenticated" and "/admin" in r[1]]
    lines = [
        "---",
        "title: Authorization coverage matrix (generated)",
        "audience: contributor",
        "---",
        "",
        "# Authorization coverage matrix",
        "",
        "**Generated** by `scripts/authz_matrix_generate.py` — do not hand-edit; "
        "regenerate after adding routes.",
        "",
        "Status is one of **role-gated** (explicit `require_*` dependency), "
        "**public** (on the unauthenticated `PUBLIC_PREFIXES` allowlist), or "
        "**authenticated** (the global auth middleware requires a logged-in "
        "principal — the safe default, not a gap).",
        "",
        f"Total routes: {len(rows)} · "
        f"role-gated: {sum(1 for r in rows if r[3] == 'role-gated')} · "
        f"public: {sum(1 for r in rows if r[3] == 'public')} · "
        f"authenticated: {sum(1 for r in rows if r[3] == 'authenticated')}",
        "",
    ]
    if admin_no_gate:
        lines += [
            "## ⚠️ Admin-path routes without a role gate",
            "",
            "These paths look privileged (contain `/admin`) but carry no "
            "`require_*` role gate — a reviewer should confirm each is meant to "
            "be reachable by any authenticated user, or add `require_admin`.",
            "",
            "| Method | Path |",
            "| --- | --- |",
            *[f"| {m} | `{p}` |" for (m, p, _g, _s) in admin_no_gate],
            "",
        ]
    lines += [
        "## All routes",
        "",
        "| Method | Path | Gate(s) | Status |",
        "| --- | --- | --- | --- |",
        *[f"| {m} | `{p}` | {g} | {s} |" for (m, p, g, s) in rows],
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    """Generate the matrix and write it to ``docs/internal/authz-matrix.md``."""
    rows = build_rows()
    out = Path(__file__).resolve().parent.parent / "docs" / "internal" / "authz-matrix.md"
    out.write_text(render_markdown(rows), encoding="utf-8")
    role_gated = sum(1 for r in rows if r[3] == "role-gated")
    admin_no_gate = sum(1 for r in rows if r[3] == "authenticated" and "/admin" in r[1])
    print(
        f"wrote {out} — {len(rows)} routes, {role_gated} role-gated, "
        f"{admin_no_gate} admin-path routes without a role gate"
    )


if __name__ == "__main__":
    main()
