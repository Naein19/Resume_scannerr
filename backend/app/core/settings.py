"""Single source of truth for all runtime configuration.

Every environment-dependent value in the app is read here once, via
pydantic-settings, instead of scattered `os.getenv()` calls. That gives us
one place to see what the app needs to run, validation at startup instead of
a KeyError three requests in, and a typed `settings` object everywhere else.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini ---
    # Google AI Studio's free tier (aistudio.google.com/apikey) is free
    # indefinitely, not a trial credit — chosen over a paid provider so this
    # project has zero run cost. Flash-tier models stay on the free tier;
    # check aistudio.google.com's model picker for the current newest Flash
    # model before deploying, since Google ships new ones faster than this
    # default gets updated.
    google_api_key: str = Field(..., description="Google AI Studio (Gemini) API key")
    # Each free-tier key has its own independent quota. Optional siblings —
    # GOOGLE_API_KEY1/2/3 — let the pipeline rotate to a fresh quota
    # instead of failing when the primary key hits a 429, without paying
    # for a higher tier. None are required; omitted ones are just not
    # part of the rotation.
    google_api_key_1: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY1")
    google_api_key_2: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY2")
    google_api_key_3: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY3")
    gemini_extraction_model: str = Field(default="gemini-2.5-flash")
    gemini_scoring_model: str = Field(default="gemini-2.5-flash")
    gemini_max_retries: int = Field(default=1, ge=0, le=3)

    @property
    def google_api_keys(self) -> list[str]:
        return [
            k
            for k in (
                self.google_api_key,
                self.google_api_key_1,
                self.google_api_key_2,
                self.google_api_key_3,
            )
            if k
        ]

    # --- Database (MongoDB) ---
    # No ORM, no migrations — collections and indexes are created/ensured
    # idempotently at startup (app/db/mongo.py:ensure_indexes), which is the
    # normal MongoDB pattern: the schema lives in the code that writes the
    # documents, not in a separate migration history.
    mongo_url: str = Field(..., description="MongoDB connection string (mongodb+srv://... for Atlas)")
    db_name: str = Field(default="Resume_Scanner")

    # --- Embedding pre-filter ---
    embedding_model_name: str = Field(default="all-MiniLM-L6-v2")
    # Below this cosine similarity, a candidate is auto-rejected before any
    # LLM scoring call runs. Tuned empirically — see README "threshold
    # tuning" section for the false-negative/cost trade-off.
    embedding_similarity_threshold: float = Field(default=0.35, ge=-1.0, le=1.0)

    # --- Uploads ---
    max_upload_size_bytes: int = Field(default=5 * 1024 * 1024)  # 5 MB
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
    )

    # --- Rate limiting ---
    rate_limit_per_minute: int = Field(default=20)

    # --- App ---
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
