from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_parse_none_str="")

    llm_provider: Literal["chatgpt_plan", "openai_api"] = "chatgpt_plan"
    chatgpt_model: str | None = None
    chatgpt_auth_dir: str = "./.chatgpt-auth"
    agent_name: str = "toefl-ai-tutor"
    oauth_callback_port: int = 1455
    frontend_url: str = "http://127.0.0.1:3000"

    openai_api_key: str | None = None
    openai_model: str | None = None
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
