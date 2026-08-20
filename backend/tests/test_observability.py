from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.domain.agbom import get_agbom_inventory

def test_tracer_lifecycle_and_spans():
    tracer = OpenTelemetryTracer()
    trace = tracer.start_trace("approval.tick", trace_id="trace_test_01")
    assert trace.trace_id == "trace_test_01"

    with tracer.start_span("observe", {"count": 5}):
        pass

    with tracer.start_span("eligibility", {"report_id": "EXP-101"}):
        pass

    completed_trace = tracer.end_trace(status="OK")
    assert completed_trace is not None
    assert len(completed_trace.spans) == 2
    assert completed_trace.spans[0].name == "observe"
    assert completed_trace.spans[0].status == "OK"
    assert completed_trace.spans[1].name == "eligibility"
    assert completed_trace.spans[1].attributes["report_id"] == "EXP-101"

def test_tracer_error_capture():
    tracer = OpenTelemetryTracer()
    tracer.start_trace("approval.tick", trace_id="trace_test_error")

    try:
        with tracer.start_span("gemini.draft"):
            raise ValueError("Test generation error")
    except ValueError:
        pass

    completed = tracer.end_trace(status="ERROR")
    assert len(completed.spans) == 1
    assert completed.spans[0].status == "ERROR"
    assert completed.spans[0].attributes["error.type"] == "ValueError"

def test_agbom_metadata_structure():
    agbom = get_agbom_inventory()
    assert agbom["agent_name"] == "ApprovalLoop"
    assert agbom["model"] == "gemini-3.5-flash"
    assert agbom["framework"] == "Google GenAI SDK (google-genai)"
    assert agbom["runtime"] == "Google Cloud Run"
    assert "deterministic_state_machine" in agbom["safety_mechanisms"]
    assert "corporate_policy_engine" in agbom["safety_mechanisms"]
