"""Behaviour tests targeting surviving mutants in the data-product-as-code
spec parser (``parse_spec``).

When the YAML source decodes to something that is not a mapping (a
scalar or a list), ``parse_spec`` rejects it with a specific, contracted
``ValueError`` message.  These tests pin that exact message text so a
mutation that blanks, re-cases, or sentinel-wraps the string is caught.
"""

from __future__ import annotations

import pytest

from pointlessql.services.data_product_as_code import parse_spec


@pytest.mark.parametrize(
    "source",
    [
        "42",  # YAML scalar -> int
        "just a bare string",  # YAML scalar -> str
        "- a\n- b\n- c",  # YAML sequence -> list
    ],
)
def test_parse_spec_non_mapping_raises_exact_message(source: str) -> None:
    """Non-mapping YAML must raise with the precise contracted message.

    The exact-string assertion distinguishes the original from every
    re-cased / blanked / sentinel-wrapped message mutant.
    """
    with pytest.raises(ValueError) as excinfo:
        parse_spec(source)
    assert str(excinfo.value) == "spec must be a YAML mapping"
