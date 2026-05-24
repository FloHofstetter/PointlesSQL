"""Unit tests for Phase 56 Jinja macros.

Covers:

* ``_macros/truncate.html`` ``truncate_cell()``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def macro_env():
    """Render the live FastAPI Jinja environment for macro round-trip."""
    from pointlessql.api.main import _TEMPLATES

    return _TEMPLATES.env


class TestTruncateCell:
    def test_below_threshold_no_truncation(self, macro_env) -> None:
        template = macro_env.from_string(
            '{% from "_macros/truncate.html" import truncate_cell %}'
            "{{ truncate_cell(text, max=10) }}"
        )
        rendered = template.render(text="short")
        assert rendered == '<span class="font-monospace small">short</span>'

    def test_at_threshold_no_truncation(self, macro_env) -> None:
        template = macro_env.from_string(
            '{% from "_macros/truncate.html" import truncate_cell %}'
            "{{ truncate_cell(text, max=5) }}"
        )
        # Length exactly equal to max stays untruncated.
        rendered = template.render(text="abcde")
        assert "…" not in rendered
        assert "pql-truncate-tip" not in rendered
        assert "abcde" in rendered

    def test_over_threshold_truncates_and_titles(self, macro_env) -> None:
        template = macro_env.from_string(
            '{% from "_macros/truncate.html" import truncate_cell %}'
            "{{ truncate_cell(text, max=10) }}"
        )
        rendered = template.render(text="this is way too long for the cell")
        assert "pql-truncate-tip" in rendered
        assert 'title="this is way too long for the cell"' in rendered
        assert "this is wa…" in rendered

    def test_none_renders_empty(self, macro_env) -> None:
        template = macro_env.from_string(
            '{% from "_macros/truncate.html" import truncate_cell %}'
            "{{ truncate_cell(text) }}"
        )
        rendered = template.render(text=None)
        assert rendered == '<span class="font-monospace small"></span>'

    def test_custom_klass(self, macro_env) -> None:
        template = macro_env.from_string(
            '{% from "_macros/truncate.html" import truncate_cell %}'
            "{{ truncate_cell(text, max=80, klass=\"text-muted\") }}"
        )
        rendered = template.render(text="hello")
        assert 'class="text-muted"' in rendered
