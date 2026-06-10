"""Cedar UID translation helpers (Phase 141)."""

from __future__ import annotations

from pointlessql.services.policy_as_code._translator import (
    build_resource_id,
    cedar_action,
    principal_uid,
)


def test_anonymous_principal() -> None:
    assert principal_uid(None) == 'User::"anonymous"'
    assert principal_uid({}) == 'User::"anonymous"'


def test_principal_uid_for_logged_in_user() -> None:
    assert principal_uid({"id": 42}) == 'User::"42"'


def test_cedar_action_passthrough() -> None:
    assert cedar_action("read") == 'Action::"read"'
    assert cedar_action("admin.manage") == 'Action::"admin.manage"'


def test_build_resource_id_data_product() -> None:
    uid = build_resource_id(resource_type="DataProduct", catalog="main", schema="silver")
    assert uid == 'DataProduct::"main.silver"'


def test_build_resource_id_data_product_missing_segments() -> None:
    uid = build_resource_id(resource_type="DataProduct", catalog="main")
    assert uid == 'DataProduct::"unknown"'


def test_build_resource_id_output_port_with_pk() -> None:
    assert build_resource_id(resource_type="OutputPort", id_value=7) == 'OutputPort::"7"'
