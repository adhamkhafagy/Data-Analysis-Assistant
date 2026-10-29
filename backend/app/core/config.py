from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://bi_platform:change-me@localhost:5432/bi_platform"
    session_secret: SecretStr = Field(default=SecretStr(""))
    frontend_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_ttl_hours: int = Field(default=168, ge=1, le=720)

    @model_validator(mode="after")
    def validate_security_settings(self):
        if len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
