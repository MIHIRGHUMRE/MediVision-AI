from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    api_key: str
    max_upload_bytes: int
    upload_file_limit: int

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            app_env=os.getenv("APP_ENV", "development").lower(),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/medivision.db"),
            api_key=os.getenv("API_KEY", "development-only-change-me"),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            upload_file_limit=int(os.getenv("UPLOAD_FILE_LIMIT", "20")),
        )

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production.")
        if self.max_upload_bytes <= 0 or self.upload_file_limit <= 0:
            raise ValueError("Upload limits must be positive integers.")
        if self.app_env == "production" and (
            len(self.api_key) < 32 or self.api_key == "development-only-change-me"
        ):
            raise ValueError("Production requires a unique API_KEY of at least 32 characters.")


settings = Settings.from_environment()
