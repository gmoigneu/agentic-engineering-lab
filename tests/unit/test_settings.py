from agentic_lab.config.settings import Settings


def test_allowlists_decode_from_json_arrays(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGENTIC_LAB_ALLOWED_REPOSITORY_IDS", "[1,2]")
    monkeypatch.setenv("AGENTIC_LAB_ALLOWED_MODEL_IDS", '["provider/model"]')
    monkeypatch.setenv("AGENTIC_LAB_ALLOWED_PROVIDER_IDS", '["Provider"]')

    settings = Settings(
        operator_token="operator",
        github_webhook_secret="webhook",
        _env_file=None,
    )

    assert settings.allowed_repository_ids == frozenset({1, 2})
    assert settings.allowed_model_ids == frozenset({"provider/model"})
    assert settings.allowed_provider_ids == frozenset({"Provider"})
