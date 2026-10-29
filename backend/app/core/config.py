from functools import lru_cache
import ipaddress

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://bi_platform:change-me@localhost:5432/bi_platform"
    session_secret: SecretStr = Field(default=SecretStr(""))
    frontend_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_ttl_hours: int = Field(default=168, ge=1, le=720)
    data_source_encryption_key: SecretStr = Field(default=SecretStr(""))
    ai_provider: str = "groq"
    groq_api_key: SecretStr = Field(default=SecretStr(""))
    groq_model: str = "llama-3.3-70b-versatile"
    data_source_allowed_hosts: str = ""
    data_source_allowed_cidrs: str = ""
    data_source_allow_private_networks: bool = False
    data_source_allow_localhost: bool = False
    data_source_connect_timeout_seconds: int = Field(default=5, ge=1, le=15)
    data_source_query_timeout_seconds: int = Field(default=5, ge=1, le=15)
    data_source_tls_mode: str = "verify-full"
    data_source_max_tables: int = Field(default=200, ge=1, le=1000)
    data_source_max_columns: int = Field(default=2000, ge=1, le=10000)
    data_source_max_concurrent_jobs: int = Field(default=4, ge=1, le=16)

    @model_validator(mode="after")
    def validate_security_settings(self):
        if len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be enabled in production")
        if self.app_env == "production" and not (self.data_source_allowed_hosts or self.data_source_allowed_cidrs):
            raise ValueError("Hosted mode requires DATA_SOURCE_ALLOWED_HOSTS or DATA_SOURCE_ALLOWED_CIDRS")
        encryption_key = self.data_source_encryption_key.get_secret_value()
        if not encryption_key:
            raise ValueError("DATA_SOURCE_ENCRYPTION_KEY is required")
        try:
            Fernet(encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            raise ValueError("DATA_SOURCE_ENCRYPTION_KEY must be a valid Fernet key") from None
        try:
            for cidr in filter(None, (item.strip() for item in self.data_source_allowed_cidrs.split(","))):
                ipaddress.ip_network(cidr, strict=False)
            if self.app_env == "production":
                for host in filter(None, (item.strip() for item in self.data_source_allowed_hosts.split(","))):
                    ipaddress.ip_address(host)
        except ValueError:
            raise ValueError("Production database allowlists must contain valid IP addresses and CIDRs") from None
        if self.data_source_tls_mode not in {"verify-full", "require", "disable"}:
            raise ValueError("DATA_SOURCE_TLS_MODE must be verify-full, require, or disable")
        if self.app_env == "production" and self.data_source_tls_mode != "verify-full":
            raise ValueError("Hosted database connections require DATA_SOURCE_TLS_MODE=verify-full")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
