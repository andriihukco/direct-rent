"""Settings loaded from the environment (and a git-ignored .env file)."""
from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    tg_api_id: int
    tg_api_hash: SecretStr
    tg_session_path: str = "data/telethon.session"
    tg_channels: Annotated[list[str], NoDecode] = []
    anthropic_api_key: SecretStr
    database_url: str
    admin_tg_id: int
    usd_uah_rate: float = 41.5
    llm_daily_max_calls: int = 500

    @field_validator("tg_channels", mode="before")
    @classmethod
    def _split_channels(cls, v: object) -> object:
        if isinstance(v, str):
            return [c.strip().lstrip("@") for c in v.split(",") if c.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
