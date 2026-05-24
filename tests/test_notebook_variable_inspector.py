"""Tests for the Variable Inspector helpers.

The kernel-side ``__pql_inspect__`` / ``__pql_inspect_detail__``
helpers are defined inline in :data:`_NOTEBOOK_BOOTSTRAP_CODE`. We
exercise them by ``exec``ing the bootstrap into a synthetic globals
dict + monkey-patching :class:`IPython.display.display` to capture
the emitted MIME bundle. The unit-level guarantees we pin:

* The helpers exist after running the bootstrap code.
* ``__pql_inspect__()`` emits ``application/x-pql-vars+json`` with
  one entry per user-visible global.
* Dunder names, modules, and plain functions are excluded; classes
  are included.
* DataFrames + sequences carry a ``shape`` / ``len`` hint.
* ``__pql_inspect_detail__`` is a no-op for unknown / dunder names.

End-to-end WS-routing of the custom MIME lives in the
``@pytest.mark.integration`` notebook tests.
"""

from __future__ import annotations

import types
from typing import Any

import pytest


@pytest.fixture
def bootstrap_ns(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Run the bootstrap inside a synthetic globals dict + capture display calls.

    Patches ``IPython.display`` in ``sys.modules`` for the duration of
    the test — the bootstrap helpers re-import display *inside* the
    function body, so the fake must remain installed when the test
    invokes them, not just when the bootstrap was first ``exec``'d.

    Returns:
        The globals dict carrying ``__pql_inspect__`` /
        ``__pql_inspect_detail__`` plus a ``_capture`` list every
        display invocation appends to.
    """
    import sys

    from pointlessql.services.notebook.kernel_session.session import (
        _NOTEBOOK_BOOTSTRAP_CODE,
    )

    captured: list[Any] = []

    def _fake_display(payload: Any, *, raw: bool = False) -> None:  # noqa: ARG001
        captured.append(payload)

    fake_module = types.ModuleType("IPython.display")
    fake_module.display = _fake_display  # type: ignore[attr-defined]
    ipython_pkg = types.ModuleType("IPython")
    ipython_pkg.display = fake_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "IPython", ipython_pkg)
    monkeypatch.setitem(sys.modules, "IPython.display", fake_module)

    g: dict[str, Any] = {
        "__name__": "__main__",
        "__builtins__": __builtins__,
    }
    exec(_NOTEBOOK_BOOTSTRAP_CODE, g)
    g["_capture"] = captured
    return g


def test_bootstrap_defines_inspect_helpers(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    assert "__pql_inspect__" in g
    assert "__pql_inspect_detail__" in g
    assert callable(g["__pql_inspect__"])
    assert callable(g["__pql_inspect_detail__"])


def test_inspect_emits_variables_with_simple_types(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    g["x"] = 42
    g["s"] = "hello"
    g["__pql_inspect__"]()
    capture = g["_capture"]
    assert len(capture) == 1
    bundle = capture[0]
    assert "application/x-pql-vars+json" in bundle
    payload = bundle["application/x-pql-vars+json"]
    names = {entry["name"] for entry in payload}
    assert {"x", "s"} <= names
    x_entry = next(e for e in payload if e["name"] == "x")
    assert x_entry["type"] == "int"
    assert x_entry["repr"] == "42"


def test_inspect_excludes_dunder_modules_and_functions(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    import math  # type: ignore[import-not-found]

    g["math_mod"] = math
    g["my_func"] = lambda: 1
    g["MyClass"] = type("MyClass", (), {})
    g["x"] = 1
    g["__pql_inspect__"]()
    bundle = g["_capture"][0]
    payload = bundle["application/x-pql-vars+json"]
    names = {entry["name"] for entry in payload}
    assert "math_mod" not in names  # modules excluded
    assert "my_func" not in names  # plain callables excluded
    assert "MyClass" in names  # but classes included
    assert "x" in names
    assert "__name__" not in names  # dunder excluded


def test_inspect_carries_shape_for_pandas_like_objects(bootstrap_ns: dict) -> None:
    g = bootstrap_ns

    class _FakeFrame:
        shape = (3, 2)

        def __len__(self) -> int:
            return 3

    g["df"] = _FakeFrame()
    g["lst"] = [1, 2, 3, 4]
    g["__pql_inspect__"]()
    payload = g["_capture"][0]["application/x-pql-vars+json"]
    df_entry = next(e for e in payload if e["name"] == "df")
    assert df_entry["shape"] == [3, 2]
    lst_entry = next(e for e in payload if e["name"] == "lst")
    assert lst_entry["len"] == 4


def test_inspect_detail_unknown_name_is_noop(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    g["__pql_inspect_detail__"]("does_not_exist")
    # No display call captured.
    assert g["_capture"] == []


def test_inspect_detail_emits_custom_mime(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    g["greeting"] = "hello"
    g["__pql_inspect_detail__"]("greeting")
    assert len(g["_capture"]) == 1
    bundle = g["_capture"][0]
    assert "application/x-pql-vardetail+json" in bundle
    detail = bundle["application/x-pql-vardetail+json"]
    assert detail["name"] == "greeting"
    assert detail["type"] == "str"
    assert "hello" in detail["repr"]


def test_inspect_detail_rejects_dunder_and_pql_helpers(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    g["__pql_inspect_detail__"]("__name__")
    g["__pql_inspect_detail__"]("__pql_inspect__")
    assert g["_capture"] == []


def test_inspect_truncates_long_reprs(bootstrap_ns: dict) -> None:
    g = bootstrap_ns
    g["long"] = "x" * 500
    g["__pql_inspect__"]()
    payload = g["_capture"][0]["application/x-pql-vars+json"]
    long_entry = next(e for e in payload if e["name"] == "long")
    assert long_entry["repr"].endswith("...")
    assert len(long_entry["repr"]) <= 200


@pytest.mark.parametrize(
    "varname",
    ["with space", "", "x-y"],
)
def test_inspect_detail_rejects_invalid_identifier(bootstrap_ns: dict, varname: str) -> None:
    g = bootstrap_ns
    g["__pql_inspect_detail__"](varname)
    assert g["_capture"] == []
