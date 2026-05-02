"""Unit tests for the provider-agnostic LLM factory."""

from __future__ import annotations

import pytest

from dronan import llm
from dronan.config import get_settings


pytestmark = pytest.mark.unit


def test_default_provider_is_openai() -> None:
    s = get_settings()
    assert s.llm_provider.lower() == "openai"


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
