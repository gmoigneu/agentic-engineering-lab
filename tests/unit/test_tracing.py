from agentic_lab.gateway.tracing import LangfuseTraceSink, TraceExporter, trace_id_for_run


class Sink:
    def __init__(self):
        self.payload = None
        self.trace_id = None

    def emit(self, trace_id, name, payload):
        self.trace_id = trace_id
        self.payload = payload


def test_trace_export_blocks_sink_when_secret_is_detected():
    sink = Sink()
    result = TraceExporter(sink).export("run", "tool", "ghp_" + "a" * 36)

    assert sink.payload is None
    assert result.trace_id is None
    assert result.detector_names == ("github_token",)


def test_trace_export_uses_deterministic_run_correlation_id():
    sink = Sink()
    result = TraceExporter(sink).export("run-123", "model", '{"provider":"StreamLake"}')

    assert sink.trace_id == trace_id_for_run("run-123")
    assert result.trace_id == sink.trace_id
    assert len(result.trace_id) == 32
    assert sink.payload == {
        "text": '{"provider":"StreamLake"}',
        "content_hash": result.content_hash,
        "redacted": False,
        "run_id": "run-123",
    }


class ObservationContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class LangfuseClient:
    def __init__(self):
        self.observation = None
        self.flushes = 0

    def start_as_current_observation(self, **kwargs):
        self.observation = kwargs
        return ObservationContext()

    def flush(self):
        self.flushes += 1


def test_langfuse_sink_emits_private_metadata_only():
    client = LangfuseClient()
    sink = LangfuseTraceSink(client)
    payload = {
        "text": '{"provider":"StreamLake"}',
        "content_hash": "a" * 64,
        "redacted": False,
        "run_id": "run-123",
    }

    sink.emit("b" * 32, "model-call", payload)

    assert client.observation == {
        "name": "model-call",
        "as_type": "generation",
        "trace_context": {"trace_id": "b" * 32},
        "metadata": payload,
    }
    assert client.flushes == 1
