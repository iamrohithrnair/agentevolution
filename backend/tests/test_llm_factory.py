"""Unit tests for the provider-agnostic LLM factory."""

from __future__ import annotations

import pytest

from dronan import llm
from dronan.config import get_settings


pytestmark = pytest.mark.unit


def test_code_default_provider_is_openai(monkeypatch, tmp_path) -> None:
    """When nothing is set, the code-level default provider is ``openai``."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    # Point pydantic-settings at an empty env file so the repo-root .env
    # (which ships with LLM_PROVIDER=google_genai) doesn't influence this test.
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    from dronan.config import Settings

    s = Settings(_env_file=str(empty_env))  # type: ignore[call-arg]
    assert s.llm_provider.lower() == "openai"


def test_active_provider_reads_env(monkeypatch) -> None:
    """Whatever ``LLM_PROVIDER`` is set to should flow through to settings."""
    from dronan import config as config_mod

    monkeypatch.setenv("LLM_PROVIDER", "google_genai")
    config_mod._settings = None
    assert get_settings().llm_provider.lower() == "google_genai"


def test_is_configured_maps_provider_to_key(monkeypatch) -> None:
    # Anthropic path
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None  # noqa: B018
    llm.get_settings.cache_clear() if hasattr(llm.get_settings, "cache_clear") else None  # noqa: B018

    # Reload settings since they're cached.
    from dronan import config as config_mod

    config_mod._settings = None  # reset the singleton

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.is_configured(llm.LLMRole.DEFAULT) is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    assert llm.is_configured(llm.LLMRole.DEFAULT) is True

    # Ollama requires no key
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    config_mod._settings = None
    assert llm.is_configured(llm.LLMRole.DEFAULT) is True


def test_get_chat_model_raises_when_unconfigured(monkeypatch) -> None:
    from dronan import config as config_mod

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_mod._settings = None

    with pytest.raises(RuntimeError, match="not configured"):
        llm.get_chat_model(llm.LLMRole.DEFAULT)


def test_role_selects_right_model_name(monkeypatch) -> None:
    from dronan import config as config_mod

    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_PLANNER_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_REFLECTION_MODEL", "o3-mini")
    config_mod._settings = None

    assert llm._resolve_model_name(llm.LLMRole.DEFAULT) == "gpt-4o"
    assert llm._resolve_model_name(llm.LLMRole.PLANNER) == "gpt-4o-mini"
    assert llm._resolve_model_name(llm.LLMRole.REFLECTION) == "o3-mini"
