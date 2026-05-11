from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="DataSage API", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    mongodb_uri: str = Field(default="mongodb://127.0.0.1:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="datasage", alias="MONGODB_DATABASE")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_refresh_secret_key: str = Field(default="change-me-refresh", alias="JWT_REFRESH_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:3000"],
        alias="CORS_ORIGINS",
    )
    encryption_key: str = Field(default="change-me-encryption", alias="ENCRYPTION_KEY")

    upload_dir: str = Field(default="backend/storage/uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=25, alias="MAX_UPLOAD_SIZE_MB")
    preview_row_limit: int = Field(default=200, alias="PREVIEW_ROW_LIMIT")
    max_user_message_tokens: int = Field(default=1200, alias="MAX_USER_MESSAGE_TOKENS")
    max_chat_result_rows: int = Field(default=200, alias="MAX_CHAT_RESULT_ROWS")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL")
    huggingface_api_key: str | None = Field(default=None, alias="HUGGINGFACE_API_KEY")
    deepseek_model: str = Field(default="deepseek-ai/DeepSeek-V4-Flash", alias="DEEPSEEK_MODEL")
    llm_timeout_seconds: int = Field(default=45, alias="LLM_TIMEOUT_SECONDS")
    deepseek_timeout_seconds: int = Field(default=90, alias="DEEPSEEK_TIMEOUT_SECONDS")

    gemini_requests_per_minute: int = Field(default=10, alias="GEMINI_REQUESTS_PER_MINUTE")
    groq_requests_per_minute: int = Field(default=28, alias="GROQ_REQUESTS_PER_MINUTE")
    deepseek_requests_per_minute: int = Field(default=5, alias="DEEPSEEK_REQUESTS_PER_MINUTE")
    gemini_tokens_per_minute: int = Field(default=30_000, alias="GEMINI_TOKENS_PER_MINUTE")
    groq_tokens_per_minute: int = Field(default=6_000, alias="GROQ_TOKENS_PER_MINUTE")
    deepseek_tokens_per_minute: int = Field(default=8_000, alias="DEEPSEEK_TOKENS_PER_MINUTE")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return ["http://127.0.0.1:3000"]

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> bool | object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
