"""App settings from environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Premarket Desk"
    secret_key: str = "change-me-in-production-use-long-random-string"
    admin_password: str = "changeme"
    database_url: str = f"sqlite:///{DATA_DIR / 'premarket.db'}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    session_hours: int = 72
    cookie_secure: bool = False
    cookie_name: str = "premarket_session"

    # Optional defaults; admin UI can override via DB settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    email_to: str = ""

    use_llm_default: bool = True
    schedule_cron: str = "15 8 * * mon-fri"  # 08:15 IST weekdays — interpreted in IST by scheduler

    # Free LLM providers (see docs/LLM_DEPLOY.md)
    llm_provider: str = "auto"  # auto | ollama | groq | gemini | openai
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "meta-llama/llama-3.1-8b-instruct:free"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
