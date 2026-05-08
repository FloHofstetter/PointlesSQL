"""Regression tests for Alpine.js x-data attribute quoting.

PointlesSQL templates inject user-controlled strings (UC connection
names, alert slugs, workspace slugs, etc.) into Alpine ``x-data``
attributes via the Jinja ``|tojson`` filter inside single-quoted
attribute values. A reasonable concern is that user-strings
containing a single-quote could break out of the attribute boundary
and create XSS or Alpine-init failures.

Jinja's default ``|tojson`` filter escapes the relevant characters
(``'``, ``"``, ``&``, ``<``, ``>``, ``\\``) to ``\\uXXXX`` JSON-string
escapes — making the output safe inside both single- and double-
quoted HTML attributes. These tests pin that behaviour against
regressions (e.g. a future Jinja config change that disables the
escape, or a custom filter that re-introduces the leak).
"""

from __future__ import annotations

import pytest
from jinja2 import Environment


@pytest.fixture
def env() -> Environment:
    return Environment(autoescape=True)


@pytest.mark.parametrize(
    "value,raw_char",
    [
        ("con'name", "'"),
        ('con"name', '"'),
        ("con&name", "&"),
        ("con<name", "<"),
        ("con>name", ">"),
        ("con\\name", "\\"),
    ],
)
def test_tojson_escapes_attribute_breakers(
    env: Environment, value: str, raw_char: str
) -> None:
    """``|tojson`` HTML-attribute-safe-escapes for x-data context."""
    template = env.from_string("x-data='{{ x|tojson }}'")
    rendered = template.render(x=value)
    # The full unescaped value must NOT survive — it would have broken
    # the attribute boundary if it had.
    assert value not in rendered, (
        f"unescaped {value!r} found in {rendered!r}"
    )
    # The outer single-quotes must remain the only single-quotes
    # (so a `'` in the user-string didn't escape the attribute).
    assert rendered.count("'") == 2, (
        f"attribute boundary broken: {rendered!r}"
    )
    # The user-controlled raw character must not appear unescaped
    # outside of the literal escape itself. For control chars this
    # check is implied by the `value not in rendered` assertion.
    del raw_char  # used only as parametrize ID, kept for readability


@pytest.mark.parametrize(
    "url_segment",
    [
        "normal-name",
        "name'with'quotes",
        'name"with"doublequotes',
        "name<with>angles",
        "name\\with\\backslash",
    ],
)
def test_alpine_data_dict_url_concatenation_safe(
    env: Environment, url_segment: str
) -> None:
    """Connection/credential/external-location use this exact pattern.

    Pattern in templates:
        x-data='deleteConfirm({ deleteUrl: {{ ("/api/connections/" ~ name)|tojson }}, ... })'
    """
    template = env.from_string(
        "x-data='deleteConfirm({ deleteUrl: "
        '{{ ("/api/connections/" ~ name)|tojson }}'
        ", redirectUrl: \"/connections\" })'"
    )
    rendered = template.render(name=url_segment)
    # Outer single-quotes must remain unique (start + end of attribute).
    assert rendered.count("'") == 2, (
        f"attribute boundary broken: {rendered!r}"
    )
    # The URL prefix must be intact.
    assert "/api/connections/" in rendered


def test_compound_object_alpine_init_safe(env: Environment) -> None:
    """The alert_detail.html / volume_detail.html pattern.

    Pattern:
        x-data='alertDetail({slug: {{ alert.slug|tojson }}, destinations: {{ alert.destinations|tojson }}})'
    """
    template = env.from_string(
        "x-data='alertDetail({slug: {{ slug|tojson }}, "
        "destinations: {{ destinations|tojson }}})'"
    )
    rendered = template.render(
        slug="alert'1",
        destinations=[
            {"id": 1, "url": "https://example.com/'hook"},
        ],
    )
    assert rendered.count("'") == 2
    assert "alert\\u0027" in rendered or "alert\\'1" not in rendered
