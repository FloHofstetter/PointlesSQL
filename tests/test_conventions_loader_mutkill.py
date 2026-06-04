"""Behaviour tests for :mod:`pointlessql.conventions._loader`.

These assert the observable contract of the two public loaders —
exact returned config values, error types + messages, the
shallow-merge replacement semantics for ``layers``, the explicit
path-vs-settings precedence, and the repo-discovery branch
(env-path short-circuit, base_dir/globs gating, the
data_product-wrapper skip, and the "first non-data-product
mapping wins" loop).

The repo-discovery path is exercised by stubbing
``pointlessql.git.discover_repo_yaml_files`` (the loader imports it
lazily inside the function body, so patching the source module is
enough); no real git checkout or SQLAlchemy session is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import pointlessql.git as gitmod
from pointlessql.config import Settings
from pointlessql.conventions._defaults import DEFAULT_CONVENTIONS
from pointlessql.conventions._loader import (
    load_conventions,
    load_conventions_for_workspace,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# load_conventions
# --------------------------------------------------------------------------


def test_no_path_returns_builtin_defaults() -> None:
    """With no explicit path and an unset settings field, the
    built-in Medallion defaults object is returned verbatim."""
    result = load_conventions(settings=Settings())
    assert result is DEFAULT_CONVENTIONS
    assert result.layer_tag_key == "layer"
    assert [layer.name for layer in result.layers] == ["bronze", "silver", "gold"]


def test_no_explicit_path_no_settings_uses_get_settings() -> None:
    """Calling with neither ``path`` nor ``settings`` must fall back
    to ``get_settings()`` (whose default conventions path is unset)
    and return the defaults — not crash.

    Kills the ``settings or get_settings()`` -> ``settings and ...``
    mutant, which would dereference ``None.conventions``.
    """
    result = load_conventions()
    assert result.layer_tag_key == "layer"
    assert len(result.layers) == 3


def test_explicit_path_overrides_scalar_field(tmp_path: Path) -> None:
    """An explicit YAML path is read and its top-level scalar
    shallow-merges over the defaults; ``layers`` (not overridden)
    stay the default three.

    Kills the path-resolution mutants (``resolved_path = None``,
    ``path and ...``), the read mutants (``raw = None``,
    ``safe_load(None)``, ``raw is not None``), and the merge mutants
    (``overrides = None``, ``merged = None``, ``merged.update(None)``,
    ``model_validate(None)``).
    """
    p = _write(tmp_path / "pointlessql.yaml", "layer_tag_key: medallion_layer\n")
    result = load_conventions(path=p, settings=Settings())
    assert result.layer_tag_key == "medallion_layer"
    assert [layer.name for layer in result.layers] == ["bronze", "silver", "gold"]


def test_explicit_path_takes_precedence_over_settings_path(tmp_path: Path) -> None:
    """When both ``path`` and ``settings.conventions.path`` are set,
    the explicit ``path`` wins (``path or settings...``)."""
    explicit = _write(tmp_path / "explicit.yaml", "layer_tag_key: from_explicit\n")
    settings_yaml = _write(tmp_path / "settings.yaml", "layer_tag_key: from_settings\n")
    settings = Settings()
    settings.conventions.path = settings_yaml
    result = load_conventions(path=explicit, settings=settings)
    assert result.layer_tag_key == "from_explicit"


def test_settings_path_used_when_no_explicit_path(tmp_path: Path) -> None:
    """When ``path`` is omitted the resolver reads
    ``settings.conventions.path``."""
    settings_yaml = _write(tmp_path / "settings.yaml", "layer_tag_key: from_settings\n")
    settings = Settings()
    settings.conventions.path = settings_yaml
    result = load_conventions(settings=settings)
    assert result.layer_tag_key == "from_settings"


def test_layers_override_replaces_the_whole_list(tmp_path: Path) -> None:
    """Overriding ``layers`` replaces the entire default list rather
    than appending — the documented shallow-merge contract."""
    p = _write(
        tmp_path / "pointlessql.yaml",
        "layers:\n"
        "  - name: raw\n"
        "    description: the only layer\n"
        "    required_audit_columns: [_x]\n",
    )
    result = load_conventions(path=p, settings=Settings())
    assert [layer.name for layer in result.layers] == ["raw"]
    assert result.get_layer("raw") is not None
    assert result.get_layer("bronze") is None
    # tag key not overridden -> default kept (field-by-field scalar merge)
    assert result.layer_tag_key == "layer"


def test_override_keys_are_preserved_not_stringified_to_none(tmp_path: Path) -> None:
    """The override-dict comprehension keys the YAML's own field
    names; a mutant that keys every entry as ``str(None)`` would drop
    the override and fall back to the default tag value."""
    p = _write(tmp_path / "pointlessql.yaml", "layer_tag_key: kept_key\n")
    result = load_conventions(path=p, settings=Settings())
    assert result.layer_tag_key == "kept_key"


def test_empty_yaml_file_returns_defaults(tmp_path: Path) -> None:
    """A YAML file whose top-level parse is ``None`` (empty / all
    comments) returns the defaults, exercising the ``raw is None``
    short-circuit."""
    p = _write(tmp_path / "pointlessql.yaml", "# just a comment\n")
    result = load_conventions(path=p, settings=Settings())
    assert result is DEFAULT_CONVENTIONS


def test_missing_file_raises_filenotfound_with_exact_message(tmp_path: Path) -> None:
    """A configured-but-absent path raises ``FileNotFoundError`` with
    the operator-facing message verbatim.

    The exact-string assertion kills every message-text mutant
    (None body, XX-wrapping, case flips, env-var rename).
    """
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError) as excinfo:
        load_conventions(path=missing, settings=Settings())
    assert str(excinfo.value) == (
        f"pointlessql.yaml not found at {missing!s} "
        "(set POINTLESSQL_CONVENTIONS_PATH= to a valid file or "
        "leave it unset to use the Medallion defaults)"
    )


def test_existing_file_does_not_raise_filenotfound(tmp_path: Path) -> None:
    """The ``not resolved_path.exists()`` guard must not fire for a
    file that *does* exist (kills the negation-removal mutant)."""
    p = _write(tmp_path / "pointlessql.yaml", "layer_tag_key: present\n")
    result = load_conventions(path=p, settings=Settings())
    assert result.layer_tag_key == "present"


def test_non_mapping_top_level_raises_value_error_with_exact_message(
    tmp_path: Path,
) -> None:
    """A top-level YAML sequence raises ``ValueError`` naming the
    actual offending type (``list``).

    The exact-string assertion kills the ``not isinstance`` flip, the
    None-message mutant, and the ``type(None).__name__`` (-> "NoneType")
    mutant.
    """
    p = _write(tmp_path / "pointlessql.yaml", "- a\n- b\n")
    with pytest.raises(ValueError) as excinfo:
        load_conventions(path=p, settings=Settings())
    assert str(excinfo.value) == (
        f"pointlessql.yaml at {p!s} must be a mapping at the top level, got list"
    )


def test_invalid_mode_string_would_break_reading(tmp_path: Path) -> None:
    """Reading a real file with the documented ``"r"`` mode succeeds;
    the value tested here is the successful read, which fails under
    the invalid-mode (``"XXrXX"`` / ``"R"``) and ``open(None, ...)``
    mutants that turn the open into a ValueError/TypeError."""
    p = _write(tmp_path / "pointlessql.yaml", "layer_tag_key: ok\n")
    result = load_conventions(path=p, settings=Settings())
    assert result.layer_tag_key == "ok"


# --------------------------------------------------------------------------
# load_conventions_for_workspace
# --------------------------------------------------------------------------


@pytest.fixture
def patched_discover(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``discover_repo_yaml_files`` with a stub.

    The stub records the kwargs it was called with (so forwarding of
    ``workspace_id`` / ``base_dir`` / ``globs`` can be asserted) and
    returns whatever ``state["matches"]`` is set to.
    """
    state: dict[str, Any] = {"matches": [], "calls": []}

    def _stub(
        factory: Any,
        *,
        workspace_id: int,
        base_dir: Path,
        globs: Sequence[str],
    ) -> list[Path]:
        state["calls"].append(
            {"workspace_id": workspace_id, "base_dir": base_dir, "globs": tuple(globs)}
        )
        return list(state["matches"])

    monkeypatch.setattr(gitmod, "discover_repo_yaml_files", _stub)
    return state


def test_workspace_env_path_short_circuits_repo_scan(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """When ``settings.conventions.path`` is set, the env yaml is
    loaded and the repo scan is never invoked.

    Kills the ``is not None`` -> ``is None`` flip and the
    ``settings=None`` forwarding mutant (which would lose the override
    and fall back to global settings -> defaults).
    """
    env_yaml = _write(tmp_path / "pointlessql.yaml", "layer_tag_key: from_env\n")
    settings = Settings()
    settings.conventions.path = env_yaml

    result = load_conventions_for_workspace(object(), workspace_id=3, settings=settings)

    assert result.layer_tag_key == "from_env"
    assert patched_discover["calls"] == []  # repo scan skipped


def test_workspace_no_base_dir_returns_defaults(
    patched_discover: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no env path and ``base_dir`` resolving to ``None`` the
    loader returns the defaults without scanning repos.

    Kills the ``base_dir is None`` -> ``is not None`` flip.
    """
    settings = Settings()
    # Force the base_dir getattr to land on the None default.
    monkeypatch.delattr(type(settings.workspace_repos), "base_dir", raising=False)
    object.__setattr__(settings.workspace_repos, "base_dir", None)

    result = load_conventions_for_workspace(object(), workspace_id=1, settings=settings)

    assert result is DEFAULT_CONVENTIONS
    assert patched_discover["calls"] == []


def test_workspace_repo_yaml_is_loaded_and_args_forwarded(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """A discovered conventions yaml (a mapping without a
    ``data_product`` wrapper) is loaded; ``workspace_id`` / ``base_dir``
    / ``globs`` are forwarded to the discovery call.

    Kills: ``base_dir = None``, ``getattr(None, ...)`` for base_dir and
    globs, wrong-attr-name getattr mutants (which empty base_dir/globs
    and yield the defaults), the ``workspace_id=None`` forwarding
    mutant, and the ``raw = None`` / ``safe_load(None)`` mutants in the
    loop body.
    """
    repo_yaml = _write(tmp_path / "repo" / "pointlessql.yaml", "layer_tag_key: from_repo\n")
    patched_discover["matches"] = [repo_yaml]

    settings = Settings()
    settings.workspace_repos.base_dir = tmp_path

    result = load_conventions_for_workspace(object(), workspace_id=42, settings=settings)

    assert result.layer_tag_key == "from_repo"
    assert len(patched_discover["calls"]) == 1
    call = patched_discover["calls"][0]
    assert call["workspace_id"] == 42
    assert call["base_dir"] == tmp_path
    assert call["globs"] == ("pointlessql.yaml", "**/pointlessql.yaml")


def test_workspace_skips_data_product_yaml(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """A discovered yaml carrying a top-level ``data_product`` key is
    NOT a conventions file and must be skipped, so the loader falls
    through to the defaults.

    Kills the ``and`` -> ``or`` flip, the ``"data_product"`` literal
    mutants, and the ``not in`` -> ``in`` flip (each of which would
    either load the data-product yaml as conventions or skip a real
    conventions yaml).
    """
    dp_yaml = _write(
        tmp_path / "repo" / "pointlessql.yaml",
        "data_product:\n  name: sales\nlayer_tag_key: should_be_ignored\n",
    )
    patched_discover["matches"] = [dp_yaml]

    settings = Settings()
    settings.workspace_repos.base_dir = tmp_path

    result = load_conventions_for_workspace(object(), workspace_id=5, settings=settings)

    assert result is DEFAULT_CONVENTIONS
    assert result.layer_tag_key == "layer"


def test_workspace_first_valid_mapping_wins_after_skip(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """The loop skips a data_product yaml and a non-mapping yaml, then
    loads the first plain conventions mapping it reaches.

    Kills the ``not in`` literal/flip mutants AND the
    ``continue`` -> ``break`` mutant (a ``break`` would abandon the
    scan at the first skipped candidate and return the defaults).
    """
    skip_dp = _write(
        tmp_path / "a" / "pointlessql.yaml",
        "data_product:\n  name: x\n",
    )
    skip_list = _write(tmp_path / "b" / "pointlessql.yaml", "- not\n- a mapping\n")
    winner = _write(tmp_path / "c" / "pointlessql.yaml", "layer_tag_key: winner\n")
    later = _write(tmp_path / "d" / "pointlessql.yaml", "layer_tag_key: too_late\n")
    patched_discover["matches"] = [skip_dp, skip_list, winner, later]

    settings = Settings()
    settings.workspace_repos.base_dir = tmp_path

    result = load_conventions_for_workspace(object(), workspace_id=9, settings=settings)

    assert result.layer_tag_key == "winner"


def test_workspace_unreadable_candidate_is_skipped_then_next_wins(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """A candidate that raises OSError on open is swallowed by the
    ``except (YAMLError, OSError): continue`` and the scan moves on.

    A ``continue`` -> ``break`` mutant would stop here and return the
    defaults instead of the second, readable yaml.
    """
    missing = tmp_path / "gone" / "pointlessql.yaml"  # never created -> OSError on open
    good = _write(tmp_path / "good" / "pointlessql.yaml", "layer_tag_key: recovered\n")
    patched_discover["matches"] = [missing, good]

    settings = Settings()
    settings.workspace_repos.base_dir = tmp_path

    result = load_conventions_for_workspace(object(), workspace_id=11, settings=settings)

    assert result.layer_tag_key == "recovered"


def test_workspace_no_matches_returns_defaults(
    tmp_path: Path, patched_discover: dict[str, Any]
) -> None:
    """An empty discovery result falls through the loop to the
    defaults."""
    patched_discover["matches"] = []
    settings = Settings()
    settings.workspace_repos.base_dir = tmp_path

    result = load_conventions_for_workspace(object(), workspace_id=2, settings=settings)

    assert result is DEFAULT_CONVENTIONS
