"""Tests for the Phase-23 contextual-help registry.

Pin the invariants the macro relies on at render time:

* every slug resolves cleanly via :func:`get_help`
* missing slugs raise ``KeyError`` (loud-fail in templates)
* title and body fit inside the Bootstrap-popover default footprint
* ``learn_more`` URLs are well-formed mkdocs paths

Templates that use the registry pass slugs as plain strings; this
test sweep is the only thing that catches a typo before it ships.
"""

from __future__ import annotations

import pytest

from pointlessql.web.help import HELP, HelpEntry, get_help


def test_every_registered_slug_resolves() -> None:
    """``get_help`` round-trips every key in :data:`HELP`."""
    for slug, entry in HELP.items():
        assert get_help(slug) is entry


def test_missing_slug_raises_keyerror() -> None:
    """A typo in a template surfaces at render time, not silently."""
    with pytest.raises(KeyError):
        get_help("does.not.exist")


@pytest.mark.parametrize("slug", sorted(HELP.keys()))
def test_slug_naming_convention(slug: str) -> None:
    """Slugs follow ``<page>.<topic>`` lowercase-kebab.

    The macro embeds the slug in HTML attribute values; restricting
    to ASCII lower + digits + ``.`` + ``-`` rules out any escape
    surprise without an explicit sanitiser pass.
    """
    assert slug == slug.lower(), f"slug {slug!r} must be lowercase"
    assert "." in slug, f"slug {slug!r} must contain a dot separator"
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    assert set(slug) <= allowed, f"slug {slug!r} contains forbidden chars"


@pytest.mark.parametrize("slug,entry", sorted(HELP.items()))
def test_entry_lengths_fit_popover(slug: str, entry: HelpEntry) -> None:
    """Title ≤ 60 chars, body ≤ 280 chars (Bootstrap popover default width)."""
    assert len(entry.title) <= 60, (
        f"slug {slug!r}: title {len(entry.title)} chars exceeds 60-char cap"
    )
    assert len(entry.body) <= 280, (
        f"slug {slug!r}: body {len(entry.body)} chars exceeds 280-char cap"
    )
    assert entry.title.strip() == entry.title, f"slug {slug!r}: title has stray whitespace"
    assert entry.body.strip() == entry.body, f"slug {slug!r}: body has stray whitespace"


@pytest.mark.parametrize("slug,entry", sorted(HELP.items()))
def test_learn_more_is_well_formed(slug: str, entry: HelpEntry) -> None:
    """``learn_more`` URLs are absolute mkdocs paths (no spaces, no ``..``)."""
    if entry.learn_more is None:
        return
    url = entry.learn_more
    assert url.startswith("/"), f"slug {slug!r}: learn_more must start with '/'"
    assert " " not in url, f"slug {slug!r}: learn_more contains whitespace"
    assert ".." not in url, f"slug {slug!r}: learn_more must not contain '..'"
    assert url == url.strip(), f"slug {slug!r}: learn_more has stray whitespace"


def test_phase23_hero_anchors_present() -> None:
    """The 5 Sprint-23.0 hero slugs are all registered.

    Sprint-23.0 wires these into runs_list, run_view, model,
    branches, and table templates.  Renaming any of them without
    updating the templates would silently break the popover.
    """
    expected = {
        "runs.what-is-a-run",
        "runs.what-is-an-operation",
        "models.what-is-promotion",
        "branches.what-is-a-delta-branch",
        "lineage.what-is-lineage",
    }
    assert expected <= set(HELP.keys()), (
        f"missing Sprint-23.0 hero slugs: {expected - set(HELP.keys())}"
    )
