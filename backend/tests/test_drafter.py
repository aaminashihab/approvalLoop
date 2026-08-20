import json
from unittest.mock import MagicMock
from decimal import Decimal
from approval_loop.domain.models import ActionType
from approval_loop.agent.drafter import GeminiAgentDrafter, DraftProposalResponse

def test_drafter_default_gemini_35_model():
    """Verify Gemini 3.5 is the default model."""
    drafter = GeminiAgentDrafter()
    assert drafter.model == "gemini-3.5-flash"

def test_drafter_custom_model_configuration(monkeypatch):
    """Verify GEMINI_MODEL environment variable overrides the model."""
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-preview")
    drafter = GeminiAgentDrafter()
    assert drafter.model == "gemini-3.5-flash-preview"

def test_drafter_explicit_model_argument():
    """Verify explicit model constructor parameter takes precedence."""
    drafter = GeminiAgentDrafter(model="gemini-3.5-flash-custom")
    assert drafter.model == "gemini-3.5-flash-custom"

def test_drafter_nudge_fallback_wording():
    """Verify deterministic fallback wording for nudge actions when offline."""
    drafter = GeminiAgentDrafter()
    wording = drafter.draft_wording(
        action_type=ActionType.NUDGE,
        report_id="EXP-101",
        submitter="Alice Chen",
        amount=Decimal("150.00"),
        currency="USD",
        description="Team lunch"
    )
    assert "EXP-101" in wording
    assert "Alice Chen" in wording
    assert "150.00" in wording
    assert "Team lunch" in wording

def test_drafter_escalation_fallback_wording():
    """Verify deterministic fallback wording for escalation actions when offline."""
    drafter = GeminiAgentDrafter()
    wording = drafter.draft_wording(
        action_type=ActionType.ESCALATE,
        report_id="EXP-102",
        submitter="Bob Miller",
        amount=Decimal("1250.00"),
        currency="USD",
        description="Cloud subscription"
    )
    assert "EXP-102" in wording
    assert "Bob Miller" in wording
    assert "1250.00" in wording
    assert "primary approver has not responded" in wording

def test_drafter_injected_mock_takes_priority():
    """Verify mock injection works for deterministic scenario tests."""
    drafter = GeminiAgentDrafter()
    mock_text = "Custom injected wording for testing"
    wording = drafter.draft_wording(
        action_type=ActionType.NUDGE,
        report_id="EXP-103",
        submitter="Carlos",
        amount=Decimal("50.00"),
        currency="USD",
        description="Snacks",
        injected_mock_response=mock_text
    )
    assert wording == mock_text

def test_drafter_structured_response_pydantic_schema():
    """Verify DraftProposalResponse schema parses valid JSON structure."""
    valid_payload = {
        "message": "Please review expense report EXP-200 for USD 500.00.",
        "tone": "professional",
        "references_report": True
    }
    proposal = DraftProposalResponse.model_validate(valid_payload)
    assert proposal.message == "Please review expense report EXP-200 for USD 500.00."
    assert proposal.tone == "professional"
    assert proposal.references_report is True

def test_drafter_live_path_malformed_json_fallback():
    """Verify that when the Gemini client returns malformed JSON, safe deterministic fallback is returned."""
    drafter = GeminiAgentDrafter(api_key="fake-key-for-mock-test")
    
    mock_response = MagicMock()
    mock_response.text = "{ invalid json syntax without closing bracket"
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    drafter.client = mock_client

    wording = drafter.draft_wording(
        action_type=ActionType.NUDGE,
        report_id="EXP-201",
        submitter="Diana",
        amount=Decimal("300.00"),
        currency="USD",
        description="Hardware purchase"
    )
    
    # Must NOT return raw malformed string
    assert "{ invalid" not in wording
    # MUST return safe deterministic fallback containing authoritative details
    assert "EXP-201" in wording
    assert "Diana" in wording
    assert "300.00" in wording
    assert "Hardware purchase" in wording

def test_drafter_live_path_structurally_invalid_schema_fallback():
    """Verify that when Gemini returns valid JSON missing the required 'message' field, fallback is returned."""
    drafter = GeminiAgentDrafter(api_key="fake-key-for-mock-test")
    
    mock_response = MagicMock()
    mock_response.text = json.dumps({"unexpected_field": "unexpected_value", "tone": "casual"})
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    drafter.client = mock_client

    wording = drafter.draft_wording(
        action_type=ActionType.ESCALATE,
        report_id="EXP-202",
        submitter="Evan",
        amount=Decimal("4500.00"),
        currency="USD",
        description="Server migration"
    )
    
    # Must NOT return raw json text
    assert "unexpected_field" not in wording
    # MUST return safe deterministic fallback
    assert "EXP-202" in wording
    assert "Evan" in wording
    assert "primary approver has not responded" in wording

def test_drafter_live_path_valid_structured_json_success():
    """Verify that valid structured JSON from Gemini is parsed and message is extracted."""
    drafter = GeminiAgentDrafter(api_key="fake-key-for-mock-test")
    
    expected_message = "Good morning Sarah, please review expense report EXP-203 submitted by Fiona for USD 800.00."
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "message": expected_message,
        "tone": "professional",
        "references_report": True
    })
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    drafter.client = mock_client

    wording = drafter.draft_wording(
        action_type=ActionType.NUDGE,
        report_id="EXP-203",
        submitter="Fiona",
        amount=Decimal("800.00"),
        currency="USD",
        description="Design software"
    )
    
    assert wording == expected_message

def test_drafter_live_path_markdown_code_fence_json_success():
    """Verify that JSON wrapped in markdown code blocks is stripped and parsed correctly."""
    drafter = GeminiAgentDrafter(api_key="fake-key-for-mock-test")
    
    expected_message = "Action required on expense report EXP-204 for George."
    mock_response = MagicMock()
    mock_response.text = f"```json\n{{\"message\": \"{expected_message}\", \"tone\": \"professional\", \"references_report\": true}}\n```"
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    drafter.client = mock_client

    wording = drafter.draft_wording(
        action_type=ActionType.NUDGE,
        report_id="EXP-204",
        submitter="George",
        amount=Decimal("95.00"),
        currency="USD",
        description="Office supplies"
    )
    
    assert wording == expected_message
