"""Pydantic Settings for Dronan. Reads from repo-root .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # MongoDB
    mongodb_uri: str = Field(default="", alias="MONGODB_URI")
    mongodb_db: str = Field(default="dronan", alias="MONGODB_DB")
    mongodb_repl_set: str = Field(default="", alias="MONGODB_REPL_SET")
    mongodb_tls_ca_file: str = Field(default="", alias="MONGODB_TLS_CA_FILE")
    mongodb_tls_allow_invalid: bool = Field(default=False, alias="MONGODB_TLS_ALLOW_INVALID")

    # Atlas Admin
    atlas_project_id: str = Field(default="", alias="ATLAS_PROJECT_ID")
    atlas_private_key: str = Field(default="", alias="ATLAS_PRIVATE_KEY")
    atlas_public_key: str = Field(default="", alias="ATLAS_PUBLIC_KEY")
    atlas_cluster_name: str = Field(default="Cluster0", alias="ATLAS_CLUSTER_NAME")

    # Voyage AI
    voyage_api_key: str = Field(default="", alias="VOYAGE_API_KEY")
    voyage_model: str = Field(default="voyage-3-large", alias="VOYAGE_MODEL")
    voyage_dim: int = Field(default=1024, alias="VOYAGE_DIM")

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_planner_model: str = Field(default="gpt-4o", alias="LLM_PLANNER_MODEL")
    llm_reflection_model: str = Field(default="gpt-4o-mini", alias="LLM_REFLECTION_MODEL")

    # Voice
    livekit_url: str = Field(default="", alias="LIVEKIT_URL")
    livekit_api_key: str = Field(default="", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(default="", alias="LIVEKIT_API_SECRET")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(default="eleven_turbo_v2_5", alias="ELEVENLABS_MODEL_ID")
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    deepgram_model: str = Field(default="nova-3", alias="DEEPGRAM_MODEL")
    elevenlabs_voice_id_multilingual: str = Field(
        default="", alias="ELEVENLABS_VOICE_ID_MULTILINGUAL"
    )

    # Voice loop tuning (prompts/06 §5)
    narration_debounce_ms: int = Field(default=600, alias="NARRATION_DEBOUNCE_MS")
    narration_suppress_near_barge_in_ms: int = Field(
        default=250, alias="NARRATION_SUPPRESS_NEAR_BARGE_IN_MS"
    )
    voice_loop_p50_budget_ms: int = Field(default=600, alias="VOICE_LOOP_P50_BUDGET_MS")
    voice_loop_p95_budget_ms: int = Field(default=900, alias="VOICE_LOOP_P95_BUDGET_MS")

    # Optional
    openweather_api_key: str = Field(default="", alias="OPENWEATHER_API_KEY")
    google_maps_api_key: str = Field(default="", alias="GOOGLE_MAPS_API_KEY")
    airsim_enabled: bool = Field(default=False, alias="AIRSIM_ENABLED")
    px4_enabled: bool = Field(default=False, alias="PX4_ENABLED")

    # App
    app_env: Literal["demo", "dev", "prod"] = Field(default="demo", alias="APP_ENV")
    api_port: int = Field(default=8000, alias="API_PORT")
    web_port: int = Field(default=3000, alias="WEB_PORT")
    next_public_api_base: str = Field(default="http://localhost:8000", alias="NEXT_PUBLIC_API_BASE")
    next_public_ws_base: str = Field(default="ws://localhost:8000", alias="NEXT_PUBLIC_WS_BASE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Encryption
    qe_kms_provider: str = Field(default="local", alias="QE_KMS_PROVIDER")
    qe_local_key: str = Field(default="", alias="QE_LOCAL_KEY")

    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT

    def voice_keys_present(self) -> bool:
        """True iff all three real-voice creds are populated.

        Used by the worker + the demo orchestrator to decide whether to wire
        LiveKit/Deepgram/ElevenLabs or fall back to the ``--text-mode`` REPL.
        """
        return bool(self.livekit_url and self.deepgram_api_key and self.elevenlabs_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def atlas_uri_from_env() -> str | None:
    """Back-compat helper matching backend/atlas_ping.py."""
    return (
        os.environ.get("MONGODB_URI")
        or os.environ.get("MONGODB_ATLAS_URI")
        or os.environ.get("ATLAS_CONNECTION_STRING")
    )
