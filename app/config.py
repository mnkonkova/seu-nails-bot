from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SLOT_HOURS = tuple(range(8, 23))
TIMEZONE = "Europe/Moscow"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_usernames: Annotated[frozenset[str], NoDecode]
    sheets_spreadsheet_id: str
    sheets_credentials_path: str = "/app/credentials/gsheets.json"
    db_path: str = "/app/data/lubabot.db"
    log_level: str = "INFO"
    error_report_username: str = "mashakon"

    @field_validator("admin_usernames", mode="before")
    @classmethod
    def _split_admins(cls, v: object) -> object:
        if isinstance(v, str):
            return frozenset(u.strip().lstrip("@").lower() for u in v.split(",") if u.strip())
        return v


settings = Settings()  # type: ignore[call-arg]
