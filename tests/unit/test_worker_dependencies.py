from agentic_lab.config.settings import Settings
from agentic_lab.gateway.github import GitHubAppBranchWriter
from agentic_lab.gateway.tracing import LangfuseTraceSink
from agentic_lab.runs import worker
from agentic_lab.runs.worker import build_dependencies


def test_worker_provider_requires_key_and_pinned_model():
    missing = Settings(operator_token="operator", github_webhook_secret="webhook")
    assert build_dependencies(missing).model_gateway is None
    configured = Settings(
        operator_token="operator",
        github_webhook_secret="webhook",
        openrouter_api_key="key",
        allowed_model_ids=frozenset({"model@1"}),
    )
    assert build_dependencies(configured).model_id == "model@1"


def test_worker_builds_the_narrow_github_app_writer_only_in_the_trusted_process() -> None:
    configured = Settings(
        operator_token="operator",
        github_webhook_secret="webhook",
        github_app_id=1,
        github_private_key="private-key-placeholder",
        allowed_repository_ids=frozenset({1}),
    )

    dependencies = build_dependencies(configured)

    assert isinstance(dependencies.branch_writer, GitHubAppBranchWriter)


def test_worker_builds_private_langfuse_trace_exporter(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(worker, "Langfuse", Client)
    configured = Settings(
        operator_token="operator",
        github_webhook_secret="webhook",
        openrouter_api_key="key",
        allowed_model_ids=frozenset({"model@1"}),
        allowed_provider_ids=frozenset({"StreamLake"}),
        langfuse_public_key="public",
        langfuse_secret_key="secret",
        langfuse_host="https://trace.example.test",
        environment="test",
    )

    dependencies = build_dependencies(configured)

    assert dependencies.model_gateway is not None
    assert isinstance(dependencies.model_gateway.trace_exporter.sink, LangfuseTraceSink)
    assert captured == {
        "public_key": "public",
        "secret_key": "secret",
        "base_url": "https://trace.example.test",
        "environment": "test",
    }
