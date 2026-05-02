"""Provider-agnostic chat model factory.

Uses ``langchain.chat_models.init_chat_model`` so we can switch from
OpenAI to Anthropic, Google, Mistral, Groq, Ollama, etc. by changing
``LLM_PROVIDER`` (and ``LLM_MODEL`` / ``LLM_PLANNER_MODEL`` /
``LLM_REFLECTION_MODEL``) in ``.env``.

Supported provider values match LangChain's ``model_provider``
argument:

* ``openai``       — needs ``OPENAI_API_KEY``
* ``anthropic``    — needs ``ANTHROPIC_API_KEY``
* ``google_genai`` — needs ``GOOGLE_API_KEY``
* ``groq``         — needs ``GROQ_API_KEY``
* ``ollama``       — local, no key (needs ``OLLAMA_HOST`` if not default)
* ``azure_openai`` — needs ``AZURE_OPENAI_API_KEY`` + endpoint

Any provider LangChain supports works; we don't hard-code the list.
"""

from __future__ import annotations

import logging
from enum import Enum

from .config import get_settings

log = logging.getLogger(__name__)


class LLMRole(str, Enum):
    """Which model variant to fetch. Matches the ``LLM_*`` env vars."""

    DEFAULT = "default"        # LLM_MODEL
    PLANNER = "planner"        # LLM_PLANNER_MODEL
    REFLECTION = "reflection"  # LLM_REFLECTION_MODEL


def _resolve_model_name(role: LLMRole) -> str:
    s = get_settings()
    if role is LLMRole.PLANNER:
        return s.llm_planner_model or s.llm_model
    if role is LLMRole.REFLECTION:
        return s.llm_reflection_model or s.llm_model
    return s.llm_model


def is_configured(role: LLMRole = LLMRole.DEFAULT) -> bool:
    """True when the active provider has its API key in env."""
    s = get_settings()
    provider = (s.llm_provider or "openai").lower()
    import os

    if provider == "openai":
        return bool(s.openai_api_key or os.environ.get("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider in ("google_genai", "google"):
        return bool(os.environ.get("GOOGLE_API_KEY"))
    if provider == "groq":
        return bool(os.environ.get("GROQ_API_KEY"))
    if provider == "ollama":
        return True  # local; no key required
    if provider in ("azure_openai", "azure"):
        return bool(os.environ.get("AZURE_OPENAI_API_KEY"))
    # Unknown provider — let ``init_chat_model`` handle it and surface a clear error.
    return True


def get_chat_model(
    role: LLMRole = LLMRole.DEFAULT,
    *,
    temperature: float = 0.2,
    **kwargs,
):
    """Return a LangChain ``BaseChatModel`` for the given role.

    Raises ``RuntimeError`` when the active provider isn't configured so
    callers can fall back cleanly (e.g. deterministic stubs).
    """
    if not is_configured(role):
        raise RuntimeError(
            "LLM provider not configured — set the provider's API key (or change LLM_PROVIDER)."
        )

    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    s = get_settings()
    provider = (s.llm_provider or "openai").lower()
    model = _resolve_model_name(role)

    # Pass the OpenAI-compatible base_url when the provider is openai and a
    # custom base is configured (useful for Azure-compatible proxies and the
    # "openai://" fork on ollama).
    init_kwargs: dict = {"model_provider": provider, "temperature": temperature}
    if provider == "openai" and s.openai_base_url:
        init_kwargs["base_url"] = s.openai_base_url
    init_kwargs.update(kwargs)

    log.debug("init_chat_model(model=%s, provider=%s, kwargs=%s)", model, provider, init_kwargs)
    return init_chat_model(model, **init_kwargs)


__all__ = ["LLMRole", "get_chat_model", "is_configured"]
