from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./delphi.db"
    secret_key: str = "dev-secret-key-change-in-production"
    invite_code: str = "worldcup2026"
    tournament_start: datetime = datetime(2026, 6, 11, 18, 0, 0, tzinfo=timezone.utc)
    admin_username: str = ""

    def is_locked(self) -> bool:
        """Return True if predictions are locked (tournament has started)."""
        now = datetime.now(tz=timezone.utc)
        ts = self.tournament_start
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return now >= ts


settings = Settings()
