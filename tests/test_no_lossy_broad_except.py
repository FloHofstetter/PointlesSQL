"""Sprint 44.2 AST-lint guard against traceback-losing broad-except sites.

Walks every ``except Exception``/``except BaseException`` /
bare-``except`` handler in ``pointlessql/`` and checks the body.

PASS conditions (ordered):

1. **Bucket A:** body contains ``logger.exception(...)`` — best
   form, single-line, traceback included.
2. **Bucket B:** body contains a logger call with ``exc_info=``
   keyword (``logger.warning("foo", exc_info=True)``,
   ``logger.error("foo", exc_info=exc)``).
3. **Bucket E:** body contains a ``raise`` statement (re-raise or
   chained ``raise X from exc``).
4. **Allowlist marker:** the ``except`` line — or any of the four
   lines above it — carries a ``# bare-broad-ok:`` comment.

FAIL conditions:

- **Bucket C (lossy):** logger call with the bound exception name
  as positional arg but no ``exc_info=`` (``logger.warning("foo:
  %s", exc)``).
- **Bucket D (silent without opt-out):** body has no logger call
  AND no ``raise`` AND no allowlist comment.

The check runs in pure ``ast`` + line-content scan, no astroid
dep.  Pre-existing 142 well-formed sites pass; the 36 Bucket-C +
~11 silent-without-marker sites fail until Sprint 44.2 converts
them.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCAN_ROOT = _REPO_ROOT / "pointlessql"
_ALLOWLIST_MARKER = "# bare-broad-ok:"
_LOGGING_LEVEL_METHODS = {"warning", "error", "info", "debug", "critical", "log"}


def _is_broad_except(handler: ast.ExceptHandler) -> bool:
    """True when *handler* catches ``Exception`` / ``BaseException`` / bare."""
    if handler.type is None:
        return True
    name = ast.unparse(handler.type)
    # Tuple form: ``except (Exception, KeyError)`` — broad iff any element is broad.
    return name in {"Exception", "BaseException"} or "Exception" in name.split(",")


def _bound_name(handler: ast.ExceptHandler) -> str | None:
    """Return the ``as <name>`` binding, or ``None`` when omitted."""
    return handler.name


def _body_has_raise(body: list[ast.stmt]) -> bool:
    """True when *body* contains a ``raise`` statement at any depth."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
    return False


def _body_has_logger_exception_or_exc_info(body: list[ast.stmt]) -> bool:
    """True when *body* preserves the traceback via stdlib logging APIs."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if not isinstance(node, ast.Call):
            continue
        # ``something.exception(...)`` — Bucket A.
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "exception"
        ):
            return True
        # Any call with ``exc_info=`` keyword — Bucket B.
        for kw in node.keywords:
            if kw.arg == "exc_info":
                return True
    return False


def _body_has_lossy_logger_call(body: list[ast.stmt], bound: str | None) -> bool:
    """True when *body* logs the bound exception WITHOUT ``exc_info=``.

    The classic foot-gun is
    ``logger.warning("op failed: %s", exc)`` — the ``%s``-formatted
    exception string lands in the message, but the traceback is
    lost.  We detect any logger-level call that takes the bound
    exception name as a positional arg without an ``exc_info``
    keyword.
    """
    if bound is None:
        return False
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _LOGGING_LEVEL_METHODS:
            continue
        # Skip if exc_info= is present (covered by Bucket B above).
        if any(kw.arg == "exc_info" for kw in node.keywords):
            continue
        # Bound exception name appears as positional arg → lossy.
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == bound:
                return True
    return False


def _has_allowlist_marker(source_lines: list[str], handler: ast.ExceptHandler) -> bool:
    """True when an ``# bare-broad-ok:`` comment shields *handler*.

    Window covers the four lines preceding the ``except`` plus the
    ``except`` line itself plus every line of the handler body.
    Same-line trailing comments and inline comments anywhere in
    the body all work.  The marker is intended to live next to
    the silent statement (``return`` / ``pass`` / ``continue``)
    that explains why no log line is emitted.
    """
    pre_start = max(0, handler.lineno - 5)
    pre_end = handler.lineno
    body_end = (handler.end_lineno or handler.lineno) + 1
    window_indices = list(range(pre_start, pre_end)) + list(range(pre_end - 1, body_end))
    for idx in window_indices:
        if 0 <= idx < len(source_lines) and _ALLOWLIST_MARKER in source_lines[idx]:
            return True
    return False


def _classify(
    handler: ast.ExceptHandler, source_lines: list[str]
) -> tuple[str, str | None]:
    """Return (verdict, reason).  verdict is ``"pass"`` or ``"fail"``."""
    body = handler.body
    if _body_has_logger_exception_or_exc_info(body):
        return "pass", "bucket-A-or-B"
    if _body_has_raise(body):
        return "pass", "bucket-E-raise"
    bound = _bound_name(handler)
    if _body_has_lossy_logger_call(body, bound):
        return "fail", "bucket-C-lossy-log"
    if _has_allowlist_marker(source_lines, handler):
        return "pass", "allowlist-marker"
    return "fail", "bucket-D-silent-without-marker"


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return every (lineno, reason) tuple where *path* fails the lint."""
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_except(node):
            continue
        verdict, reason = _classify(node, source_lines)
        if verdict == "fail":
            assert reason is not None
            offenders.append((node.lineno, reason))
    return offenders


def test_no_lossy_or_silent_broad_except_in_pointlessql() -> None:
    """Every broad-except site preserves the traceback or carries opt-out marker."""
    failures: list[tuple[Path, int, str]] = []
    for path in sorted(_SCAN_ROOT.rglob("*.py")):
        for lineno, reason in _scan_file(path):
            failures.append((path, lineno, reason))
    if failures:
        rendered = "\n".join(
            f"  {path.relative_to(_REPO_ROOT)}:{lineno}: {reason}"
            for path, lineno, reason in failures
        )
        raise AssertionError(
            "Broad-except sites without traceback preservation or "
            "``# bare-broad-ok:`` opt-out marker:\n"
            f"{rendered}\n"
            "Fix: convert ``logger.warning('...: %s', exc)`` to "
            "``logger.exception('...')``, or add the comment."
        )
