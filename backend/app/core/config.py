"""Application settings via pydantic-settings — reads from .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://admin:changeme@db:5432/localization"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    GATEWAY_API_KEY: str = "dev-gateway-key-change-in-production"
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
