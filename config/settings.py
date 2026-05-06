"""Configuration settings for environment-driven app behavior."""

from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/processed/ai_job_agent.db"
    resume_tailor_api_base_url: str = "http://localhost:8000"
    resume_tailor_profile_id: str = "profile_example"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database_url=os.getenv(
                "DATABASE_URL", "sqlite:///./data/processed/ai_job_agent.db"
            ),
            resume_tailor_api_base_url=os.getenv(
                "RESUME_TAILOR_API_BASE_URL", "http://localhost:8000"
            ),
            resume_tailor_profile_id=os.getenv(
                "RESUME_TAILOR_PROFILE_ID", "profile_example"
            ),
        )

