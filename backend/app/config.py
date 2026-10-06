from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_parse_none_str="")

    llm_provider: Literal["codex_cli", "openai_api"] = "codex_cli"
    codex_bin: str = "codex"
    codex_model: str = ""

    openai_api_key: str = ""
    openai_model: str = ""
    llm_temperature: float | None = 0.0
    llm_task_temperature: float = 0.9
    llm_timeout_s: float = 30.0
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0

    database_url: str = "sqlite:///./tutor.db"
    agent_max_steps: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
