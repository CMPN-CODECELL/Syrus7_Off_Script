"""
Syrus Backend — Configuration
Reads from environment variables / .env file
"""
from pydantic_settings import BaseSettings
from pydantic import Field
import secrets


class Settings(BaseSettings):
    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # Security
    # A process-local fallback keeps the local mock demo bootable without
    # storing another secret. Set APPROVAL_TOKEN_SECRET for stable deployments.
    approval_token_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    approval_token_ttl_seconds: int = 60  # token expires in 60 seconds

    # Database
    database_url: str = "postgresql+asyncpg://syrus:syrus_secret@localhost:5432/syrus"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Mock API
    mock_api_url: str = "http://localhost:8001"

    # App
    app_name: str = "Syrus Trading Copilot"
    debug: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
