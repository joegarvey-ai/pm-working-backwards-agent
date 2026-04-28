"""Shape checks for compliance-related enums in brd_intermediate.

Locks the member names, string values, and ordering map against the
constrained sets defined in the compliance-aware-brd design.
"""

import pytest

from pm_agent_system.models import DataClassification, GateOwner
from pm_agent_system.models.brd_intermediate import _DATA_CLASS_ORDER


def test_data_classification_members_and_values():
    expected = {
        "PUBLIC": "Public",
        "CONFIDENTIAL": "Confidential",
        "HIGHLY_CONFIDENTIAL": "Highly Confidential",
        "RESTRICTED": "Restricted",
        "CRITICAL": "Critical",
    }
    actual = {m.name: m.value for m in DataClassification}
    assert actual == expected


def test_gate_owner_members_and_values():
    expected = {
        "PM": "PM",
        "TECH_LEAD": "Tech Lead",
        "ENGINEER": "Engineer",
        "LEGAL": "Legal",
        "SECURITY": "Security",
        "PRIVACY": "Privacy",
    }
    actual = {m.name: m.value for m in GateOwner}
    assert actual == expected


def test_data_classification_is_str_enum():
    assert issubclass(DataClassification, str)
    assert DataClassification.PUBLIC == "Public"


def test_gate_owner_is_str_enum():
    assert issubclass(GateOwner, str)
    assert GateOwner.LEGAL == "Legal"


def test_data_class_order_covers_all_members_and_is_strictly_increasing():
    # Every member must have an integer rank.
    assert set(_DATA_CLASS_ORDER.keys()) == set(DataClassification)
    assert all(isinstance(v, int) for v in _DATA_CLASS_ORDER.values())

    # Ranks must follow Public < Confidential < Highly Confidential < Restricted < Critical.
    expected_order = [
        DataClassification.PUBLIC,
        DataClassification.CONFIDENTIAL,
        DataClassification.HIGHLY_CONFIDENTIAL,
        DataClassification.RESTRICTED,
        DataClassification.CRITICAL,
    ]
    ranks = [_DATA_CLASS_ORDER[m] for m in expected_order]
    assert ranks == [0, 1, 2, 3, 4]
    assert ranks == sorted(set(ranks))


def test_unknown_data_classification_value_rejected():
    with pytest.raises(ValueError):
        DataClassification("Top Secret")


def test_unknown_gate_owner_value_rejected():
    with pytest.raises(ValueError):
        GateOwner("Intern")
