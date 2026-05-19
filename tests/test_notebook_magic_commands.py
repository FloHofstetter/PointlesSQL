"""Tests for the Phase-98.A magic-command pre-processor."""

from __future__ import annotations

from pointlessql.services.notebook import magic_commands


def test_has_magics_negative() -> None:
    """Plain Python source short-circuits without scanning."""
    assert magic_commands.has_magics("x = 1\nprint(x)\n") is False


def test_has_magics_positive() -> None:
    """Detect %sql / %md / %fs ls / %timeit prefixes."""
    assert magic_commands.has_magics("%sql SELECT 1") is True
    assert magic_commands.has_magics("%md hello") is True
    assert magic_commands.has_magics("%%md\n# heading") is True
    assert magic_commands.has_magics("%fs ls /tmp") is True
    assert magic_commands.has_magics("%timeit 1+1") is True


def test_preprocess_md_line() -> None:
    """``%md`` line-magic emits a kernel-helper call with the literal."""
    res = magic_commands.preprocess("%md hello world")
    assert res.source == "__pql_magic_md__('hello world')"
    assert res.used == ["md"]
    assert res.sql_blocks == []


def test_preprocess_md_block() -> None:
    """``%%md`` block-magic captures all lines until end-of-cell."""
    src = "%%md\n# heading\n* item one\n* item two\n"
    res = magic_commands.preprocess(src)
    assert "heading" in res.source
    assert res.used == ["md"]


def test_preprocess_fs_ls() -> None:
    """``%fs ls /path`` becomes a call to ``__pql_magic_fs_ls__``."""
    res = magic_commands.preprocess("%fs ls /tmp")
    assert res.source == "__pql_magic_fs_ls__('/tmp')"
    assert res.used == ["fs_ls"]


def test_preprocess_timeit() -> None:
    """``%timeit expr`` becomes a call to ``__pql_magic_timeit__``."""
    res = magic_commands.preprocess("%timeit sum(range(100))")
    assert res.source == "__pql_magic_timeit__('sum(range(100))')"
    assert res.used == ["timeit"]


def test_preprocess_sql_emits_placeholder() -> None:
    """``%sql`` becomes a ``__PQL_SQL_BLOCK_<n>__`` sentinel until resolution."""
    res = magic_commands.preprocess("%sql SELECT 1 FROM main.public.foo")
    assert "__PQL_SQL_BLOCK_0__" in res.source
    assert len(res.sql_blocks) == 1
    assert res.sql_blocks[0].sql == "SELECT 1 FROM main.public.foo"
    assert res.sql_blocks[0].result_var is None


def test_preprocess_sql_with_result_var_flag() -> None:
    """``%sql -o df SELECT …`` captures the result-var flag."""
    res = magic_commands.preprocess("%sql -o orders SELECT * FROM x.y.z")
    assert len(res.sql_blocks) == 1
    assert res.sql_blocks[0].result_var == "orders"
    assert res.sql_blocks[0].sql == "SELECT * FROM x.y.z"


def test_preprocess_mixed_python_and_magics() -> None:
    """Plain Python lines pass through; magic lines are transformed."""
    src = "import os\n%md heading\nprint('done')\n"
    res = magic_commands.preprocess(src)
    lines = res.source.splitlines()
    assert lines[0] == "import os"
    assert "__pql_magic_md__" in lines[1]
    assert lines[2] == "print('done')"


def test_preprocess_preserves_indentation() -> None:
    """Indented magic lines keep their leading whitespace."""
    src = "if True:\n    %md inside-block\n"
    res = magic_commands.preprocess(src)
    assert "    __pql_magic_md__('inside-block')" in res.source


def test_preprocess_empty_magic_is_safe() -> None:
    """Bare ``%md`` / empty ``%sql`` degrade to comments — never raise."""
    res_md = magic_commands.preprocess("%md")
    assert "# %md (empty)" in res_md.source
    res_sql = magic_commands.preprocess("%sql ")
    assert "# %sql (empty)" in res_sql.source


def test_apply_sql_resolutions_replaces_placeholders_in_order() -> None:
    """Multiple ``%sql`` blocks splice in order from the wrappers list."""
    src = "%sql SELECT 1\n%sql SELECT 2\n"
    pre = magic_commands.preprocess(src)
    final = magic_commands.apply_sql_resolutions(
        pre.source,
        wrappers=["RUN_A()", "RUN_B()"],
    )
    assert "RUN_A()" in final
    assert "RUN_B()" in final
    assert "__PQL_SQL_BLOCK_" not in final


def test_apply_sql_resolutions_idempotent_when_no_blocks() -> None:
    """No SQL blocks → source returned untouched."""
    res = magic_commands.preprocess("x = 1\n")
    out = magic_commands.apply_sql_resolutions(res.source, wrappers=[])
    assert out == "x = 1"
