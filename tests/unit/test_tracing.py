from agentic_lab.gateway.tracing import TraceExporter


class Sink:
    def __init__(self):
        self.payload = None

    def emit(self, trace_id, name, payload):
        self.payload = payload


def test_trace_export_redacts_before_sink():
    sink = Sink()
    TraceExporter(sink).export("run", "tool", "ghp_" + "a" * 36)
    assert "ghp_" not in sink.payload["text"]
    assert sink.payload["redacted"]
