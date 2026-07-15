from agentic_lab.config.settings import Settings
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
