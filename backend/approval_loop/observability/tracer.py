import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from contextlib import contextmanager
from pydantic import BaseModel, Field

logger = logging.getLogger("approval_loop.tracer")

# Attempt genuine OpenTelemetry SDK integration
try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import Status, StatusCode
    HAS_OTEL_SDK = True
except ImportError:
    HAS_OTEL_SDK = False

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class SpanRecord(BaseModel):
    span_id: str = Field(default_factory=lambda: f"span_{uuid.uuid4().hex[:8]}")
    trace_id: str
    name: str
    start_time: str
    end_time: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "OK"  # "OK" | "ERROR" | "BLOCKED" | "DENIED"
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

class TraceRecord(BaseModel):
    trace_id: str
    root_name: str
    start_time: str
    end_time: Optional[str] = None
    duration_ms: float = 0.0
    spans: list[SpanRecord] = Field(default_factory=list)
    status: str = "OK"

class OpenTelemetryTracer:
    """
    OpenTelemetry-Integrated Execution Tracer:
    Bridges autonomous lifecycle execution directly to OpenTelemetry SDK standards
    while maintaining a high-performance in-memory ring buffer for UI observability.
    Spans traced:
    observe -> eligibility -> skill.load -> claim -> gemini.draft -> validation -> policy.check -> notification -> state_transition
    """
    _instance = None

    def __init__(self, max_stored_traces: int = 100):
        self.max_stored_traces = max_stored_traces
        self.traces: list[TraceRecord] = []
        self._current_trace: Optional[TraceRecord] = None
        self._otel_tracer = None
        if HAS_OTEL_SDK:
            try:
                self._otel_tracer = otel_trace.get_tracer("approval-loop", "2.1.0")
            except Exception as e:
                logger.warning("Could not initialize OTel SDK tracer: %s", str(e))

    @classmethod
    def get_tracer(cls) -> "OpenTelemetryTracer":
        if cls._instance is None:
            cls._instance = OpenTelemetryTracer()
        return cls._instance

    def start_trace(self, root_name: str, trace_id: Optional[str] = None) -> TraceRecord:
        t_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        trace = TraceRecord(
            trace_id=t_id,
            root_name=root_name,
            start_time=utc_now_iso()
        )
        self._current_trace = trace
        return trace

    def end_trace(self, status: str = "OK"):
        if self._current_trace:
            self._current_trace.end_time = utc_now_iso()
            self._current_trace.status = status
            if self._current_trace.spans:
                self._current_trace.duration_ms = sum(s.duration_ms for s in self._current_trace.spans)
            self.traces.append(self._current_trace)
            if len(self.traces) > self.max_stored_traces:
                self.traces.pop(0)
            trace = self._current_trace
            self._current_trace = None
            return trace
        return None

    @contextmanager
    def start_span(self, name: str, attributes: Optional[dict[str, Any]] = None):
        trace_id = self._current_trace.trace_id if self._current_trace else f"trace_{uuid.uuid4().hex[:12]}"
        
        # Sanitize attributes to guarantee no secret or credential leaks
        sanitized_attrs = {}
        if attributes:
            for k, v in attributes.items():
                if any(sec in k.lower() for sec in ["key", "secret", "password", "token", "auth"]):
                    sanitized_attrs[k] = "[REDACTED]"
                else:
                    sanitized_attrs[k] = v

        span = SpanRecord(
            trace_id=trace_id,
            name=name,
            start_time=utc_now_iso(),
            attributes=sanitized_attrs
        )
        start_mono = time.perf_counter()
        
        # Optional real OpenTelemetry SDK span
        otel_span_cm = None
        if self._otel_tracer:
            try:
                otel_span_cm = self._otel_tracer.start_as_current_span(name)
            except Exception:
                otel_span_cm = None

        try:
            if otel_span_cm:
                with otel_span_cm as otel_s:
                    for k, v in sanitized_attrs.items():
                        if isinstance(v, (str, bool, int, float)):
                            otel_s.set_attribute(k, v)
                    yield span
            else:
                yield span
            span.status = "OK"
        except Exception as e:
            span.status = "ERROR"
            span.attributes["error.type"] = type(e).__name__
            span.attributes["error.message"] = str(e)
            raise
        finally:
            end_mono = time.perf_counter()
            span.end_time = utc_now_iso()
            span.duration_ms = round((end_mono - start_mono) * 1000, 2)
            if self._current_trace:
                self._current_trace.spans.append(span)

    def get_recent_traces(self, limit: int = 20) -> list[dict]:
        return [t.model_dump() for t in self.traces[-limit:]]

