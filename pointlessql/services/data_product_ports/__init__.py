"""Data-product port service layer.

Re-exports the output/input port CRUD primitives so callers do
``from pointlessql.services.data_product_ports import create_output_port``
without reaching into the private sub-module.
"""

from __future__ import annotations

from pointlessql.services.data_product_ports._crud import (
    create_input_port,
    create_output_port,
    delete_input_port,
    delete_output_port,
    list_input_ports,
    list_output_ports,
)

__all__ = [
    "create_input_port",
    "create_output_port",
    "delete_input_port",
    "delete_output_port",
    "list_input_ports",
    "list_output_ports",
]
