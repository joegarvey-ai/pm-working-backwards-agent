"""Backward-compatibility tests for CodingPromptOutput after the compliance-aware extension.

A pre-feature CodingPromptOutput payload (no ``stride_stub`` and no ``raci_matrix``)
must still validate against the extended schema, and both new fields must fall
back to their documented defaults. Payloads that do carry the new fields must
round-trip their values without loss.
"""

from pm_agent_system.models.coding_prompt_output import (
    CodingPromptOutput,
    RACIRow,
)


def _minimal_payload() -> dict:
    """Return a minimal valid CodingPromptOutput payload without the new fields."""
    return {
        "build_summary": "Build a preferences API that stores user UI settings on DynamoDB.",
        "user_flows": [
            {
                "name": "Read preferences",
                "steps": [
                    "User opens tool",
                    "Tool calls GET /preferences",
                    "Tool renders stored settings",
                ],
                "related_requirements": ["FR-001"],
            }
        ],
        "feature_specs": [
            {
                "name": "GET /preferences",
                "description": "Return stored preferences for the authenticated user.",
                "acceptance_criteria": [
                    "Given an authenticated user, when the client calls GET /preferences, then the API returns HTTP 200."
                ],
                "priority": "P0",
            }
        ],
        "target_tool": "kiro",
    }


def test_coding_prompt_output_without_new_fields_loads_successfully():
    payload = _minimal_payload()

    result = CodingPromptOutput.model_validate(payload)

    assert isinstance(result, CodingPromptOutput)


def test_coding_prompt_output_defaults_new_fields():
    payload = _minimal_payload()

    result = CodingPromptOutput.model_validate(payload)

    assert result.stride_stub == ""
    assert result.raci_matrix == []


def test_coding_prompt_output_preserves_existing_fields():
    payload = _minimal_payload()

    result = CodingPromptOutput.model_validate(payload)

    assert result.build_summary == payload["build_summary"]
    assert result.target_tool == payload["target_tool"]
    assert len(result.user_flows) == len(payload["user_flows"])
    assert len(result.feature_specs) == len(payload["feature_specs"])


def test_coding_prompt_output_with_new_fields_populated():
    payload = _minimal_payload()
    payload["stride_stub"] = "## STRIDE\n\nSpoofing: scoped via Cognito identity tokens."
    payload["raci_matrix"] = [
        {
            "role": "Security",
            "responsible": False,
            "accountable": True,
            "consulted": False,
            "informed": False,
        }
    ]

    result = CodingPromptOutput.model_validate(payload)

    assert result.stride_stub == payload["stride_stub"]
    assert len(result.raci_matrix) == 1
    assert isinstance(result.raci_matrix[0], RACIRow)
    assert result.raci_matrix[0].role == "Security"
    assert result.raci_matrix[0].accountable is True
    assert result.raci_matrix[0].responsible is False
    assert result.raci_matrix[0].consulted is False
    assert result.raci_matrix[0].informed is False
