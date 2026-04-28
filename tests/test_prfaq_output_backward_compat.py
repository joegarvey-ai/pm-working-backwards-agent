"""Backward-compatibility tests for PRFAQOutput after the compliance-aware extension.

A pre-feature PRFAQOutput payload (no ``data_handling`` field) must still
validate against the extended schema, and the new ``data_handling`` field
must fall back to an empty ``PRFAQDataHandling``. Payloads that do carry
the new field must round-trip their elements without loss.
"""

import json
from pathlib import Path

from pm_agent_system.models.compliance_primitives import DataClassification
from pm_agent_system.models.prfaq_output import (
    PRFAQDataHandling,
    PRFAQOutput,
)

FIXTURES = Path(__file__).parent / "fixtures"
WITHOUT_DATA_HANDLING_FIXTURE = FIXTURES / "prfaq_without_data_handling.json"
WITH_DATA_HANDLING_FIXTURE = FIXTURES / "prfaq_with_data_handling.json"


def _load(fixture_path: Path) -> dict:
    return json.loads(fixture_path.read_text())


def test_prfaq_without_data_handling_fixture_loads():
    payload = _load(WITHOUT_DATA_HANDLING_FIXTURE)

    result = PRFAQOutput.model_validate(payload)

    assert isinstance(result, PRFAQOutput)


def test_prfaq_without_data_handling_defaults_data_handling_field():
    payload = _load(WITHOUT_DATA_HANDLING_FIXTURE)

    result = PRFAQOutput.model_validate(payload)

    assert isinstance(result.data_handling, PRFAQDataHandling)
    assert result.data_handling.elements == []
    assert result.data_handling.gap_flag is False
    assert result.data_handling.gap_notes == []


def test_prfaq_with_data_handling_fixture_loads():
    payload = _load(WITH_DATA_HANDLING_FIXTURE)

    result = PRFAQOutput.model_validate(payload)

    assert isinstance(result, PRFAQOutput)


def test_prfaq_with_data_handling_preserves_elements():
    payload = _load(WITH_DATA_HANDLING_FIXTURE)
    source_elements = payload["data_handling"]["elements"]

    result = PRFAQOutput.model_validate(payload)

    assert len(result.data_handling.elements) == len(source_elements)
    classifications = {e.classification for e in result.data_handling.elements}
    assert DataClassification.PUBLIC in classifications
    assert DataClassification.HIGHLY_CONFIDENTIAL in classifications


def test_prfaq_without_data_handling_preserves_existing_fields():
    payload = _load(WITHOUT_DATA_HANDLING_FIXTURE)

    result = PRFAQOutput.model_validate(payload)

    assert result.press_release == payload["press_release"]
    assert len(result.external_faqs) == len(payload["external_faqs"])
    assert len(result.internal_faqs) == len(payload["internal_faqs"])
