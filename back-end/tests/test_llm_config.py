"""Cấu hình model có thể để trống và không lộ thông tin bí mật khi in Settings."""

import pytest

from app.config import BACKEND_DIR, Settings, load_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "llm-config-test-key-" + "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql://test:test@localhost/llm_config_tests")
    monkeypatch.setenv("CORS_ORIGIN", "http://localhost:4173")
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "45")
    monkeypatch.setenv("UPLOAD_DIR", "storage/documents")
    for name in ("LLM_API_KEY", "LLM_API_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_missing_llm_config_is_optional_and_preserves_other_settings():
    settings = load_settings()
    assert settings.llm_api_key == settings.llm_api_url == settings.llm_model == ""
    assert settings.cors_origins == ("http://localhost:4173",)
    assert settings.access_token_minutes == 45
    assert settings.database_url == "mysql+pymysql://test:test@localhost/llm_config_tests"
    assert settings.upload_dir == BACKEND_DIR / "storage" / "documents"


def test_blank_llm_config_does_not_require_a_provider(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_API_URL", "LLM_MODEL"):
        monkeypatch.setenv(name, " \t ")
    settings = load_settings()
    assert settings.llm_api_key == settings.llm_api_url == settings.llm_model == ""


def test_llm_config_is_trimmed_without_changing_provider_url(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "  test-provider-key  ")
    monkeypatch.setenv("LLM_API_URL", " https://provider.example.invalid/custom/chat?version=1 ")
    monkeypatch.setenv("LLM_MODEL", "  provider-model  ")
    settings = load_settings()
    assert settings.llm_api_key == "test-provider-key"
    assert settings.llm_api_url == "https://provider.example.invalid/custom/chat?version=1"
    assert settings.llm_model == "provider-model"


def test_settings_defaults_do_not_select_a_model_or_provider():
    settings = Settings()
    assert settings.llm_api_key == settings.llm_api_url == settings.llm_model == ""


def test_settings_repr_does_not_expose_llm_credentials(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "private-llm-key-test")
    monkeypatch.setenv("LLM_API_URL", "https://user:private-password@provider.example.invalid/chat?key=private-query")
    monkeypatch.setenv("LLM_MODEL", "private-deployment-name")
    settings = load_settings()
    rendered = repr(settings)
    assert settings.llm_api_key not in rendered
    assert settings.llm_api_url not in rendered
    assert "private-password" not in rendered and "private-query" not in rendered
    assert settings.llm_model not in rendered
