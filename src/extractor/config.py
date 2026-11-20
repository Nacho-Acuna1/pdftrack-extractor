"""Application settings loaded from environment variables (Twelve-Factor III)."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is injected via environment variables.

    Defaults mirror the values in ``.env.example`` and are suitable for
    local development.  In production every value MUST be supplied
    explicitly through the environment.
    """

    PORT: int = 8000
    EXTRACTION_WORKERS: int = 1
    EXTRACTION_QUEUE_SIZE: int = 1
    QUEUE_WAIT_TIMEOUT_SECONDS: float = 0
    EXTRACTION_TIMEOUT_SECONDS: float = 30
    MAX_PDF_SIZE_MB: int = 50
    LOG_LEVEL: str = "INFO"

    model_config = {"extra": "ignore"}


settings = Settings()
