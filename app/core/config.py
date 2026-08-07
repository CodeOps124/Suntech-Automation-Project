"""Central application configuration.

Reads from environment / .env via pydantic-settings. This is the single source
of truth for runtime settings; nothing else should call os.getenv directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "Suntech Form 145/146 Platform"
    app_env: str = "dev"
    debug: bool = True
    secret_key: str = "change-me"
    api_v1_prefix: str = "/api/v1"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "suntech"
    postgres_password: str = "suntech_dev_pw"
    postgres_db: str = "suntech_form145"
    database_url: str | None = None  # explicit override wins if set
    # Superuser/BYPASSRLS connection for migrations, seeds, and admin
    # bootstrap. The normal app path must NOT use this — it would silently
    # disable row-level security.
    privileged_database_url: str | None = None

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Object storage (S3-compatible)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "suntech-documents"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    # OCR
    ocr_provider: str = "stub"
    ocr_api_url: str | None = None
    ocr_api_key: str | None = None

    # Reminders
    reminder_interval_hours: int = 24
    reminder_max_included: int = 3

    # Pipeline orchestration driver.
    #   celery — the in-process default: upload queues a Celery task.
    #   n8n    — production orchestration via n8n: upload fires N8N_WEBHOOK_URL
    #            and n8n drives the case through the /internal endpoints.
    #            If the webhook call fails, we fall back to Celery so a case
    #            never stalls on orchestrator downtime.
    # Both drivers execute the SAME service layer — the rules engine, state
    # machine, RLS, and audit live in one place regardless of driver.
    pipeline_driver: str = "celery"           # celery | n8n
    n8n_webhook_url: str | None = None        # e.g. http://host.docker.internal:5678/webhook/suncomply-intake
    # Shared secret for the /internal pipeline endpoints. The app passes it to
    # n8n inside the webhook payload; n8n echoes it back on every callback.
    internal_api_token: str = "change-me-internal-token"

    # Tax rules
    active_rule_version: str = Field(default="2024.1")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """Effective SQLAlchemy URL. Explicit DATABASE_URL wins, else derived."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def privileged_sqlalchemy_url(self) -> str:
        """URL for RLS-bypassing operations (migrations/seed/admin).

        Falls back to the POSTGRES_* superuser parts. If DATABASE_URL points
        the app at a restricted role (as the compose stack does), this stays
        on the owner role.
        """
        if self.privileged_database_url:
            return self.privileged_database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
