from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env", ".env"),
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
        default_factory=lambda: ["http://127.0.0.1:3000", "http://localhost:3000"],
        alias="CORS_ORIGINS",
    )
    encryption_key: str = Field(default="change-me-encryption", alias="ENCRYPTION_KEY")

    upload_dir: str = Field(default="backend/storage/uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=25, alias="MAX_UPLOAD_SIZE_MB")
    preview_row_limit: int = Field(default=200, alias="PREVIEW_ROW_LIMIT")
    max_user_message_tokens: int = Field(default=1200, alias="MAX_USER_MESSAGE_TOKENS")
    max_chat_result_rows: int = Field(default=200, alias="MAX_CHAT_RESULT_ROWS")

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    groq_api_key_1: str | None = Field(default=None, alias="GROQ_API_KEY_1")
    groq_model_1: str | None = Field(default=None, alias="GROQ_MODEL_1")
    groq_api_key_2: str | None = Field(default=None, alias="GROQ_API_KEY_2")
    groq_model_2: str | None = Field(default=None, alias="GROQ_MODEL_2")
    groq_api_key_3: str | None = Field(default=None, alias="GROQ_API_KEY_3")
    groq_model_3: str | None = Field(default=None, alias="GROQ_MODEL_3")
    groq_api_key_4: str | None = Field(default=None, alias="GROQ_API_KEY_4")
    groq_model_4: str | None = Field(default=None, alias="GROQ_MODEL_4")
    groq_api_key_5: str | None = Field(default=None, alias="GROQ_API_KEY_5")
    groq_model_5: str | None = Field(default=None, alias="GROQ_MODEL_5")
    groq_api_key_6: str | None = Field(default=None, alias="GROQ_API_KEY_6")
    groq_model_6: str | None = Field(default=None, alias="GROQ_MODEL_6")
    groq_api_key_7: str | None = Field(default=None, alias="GROQ_API_KEY_7")
    groq_model_7: str | None = Field(default=None, alias="GROQ_MODEL_7")
    groq_api_key_8: str | None = Field(default=None, alias="GROQ_API_KEY_8")
    groq_model_8: str | None = Field(default=None, alias="GROQ_MODEL_8")
    groq_api_key_9: str | None = Field(default=None, alias="GROQ_API_KEY_9")
    groq_model_9: str | None = Field(default=None, alias="GROQ_MODEL_9")
    groq_api_key_10: str | None = Field(default=None, alias="GROQ_API_KEY_10")
    groq_model_10: str | None = Field(default=None, alias="GROQ_MODEL_10")
    huggingface_api_key: str | None = Field(default=None, alias="HUGGINGFACE_API_KEY")
    huggingface_api_base: str = Field(default="https://router.huggingface.co/v1", alias="HUGGINGFACE_API_BASE")
    deepseek_model: str = Field(default="deepseek-ai/DeepSeek-V4-Flash", alias="HUGGINGFACE_DEEPSEEK_MODEL")
    llm_default_provider: str = Field(default="groq", alias="LLM_DEFAULT_PROVIDER")
    openrouter_report_api_key: str | None = Field(default=None, alias="OPENROUTER_REPORT_API_KEY")
    openrouter_report_model: str = Field(default="openai/gpt-oss-20b:free", alias="OPENROUTER_REPORT_MODEL")
    llm_timeout_seconds: int = Field(default=45, alias="LLM_TIMEOUT_SECONDS")
    deepseek_timeout_seconds: int = Field(default=90, alias="DEEPSEEK_TIMEOUT_SECONDS")

    groq_requests_per_minute: int = Field(default=28, alias="GROQ_REQUESTS_PER_MINUTE")
    deepseek_requests_per_minute: int = Field(default=5, alias="DEEPSEEK_REQUESTS_PER_MINUTE")
    groq_tokens_per_minute: int = Field(default=6_000, alias="GROQ_TOKENS_PER_MINUTE")
    deepseek_tokens_per_minute: int = Field(default=8_000, alias="DEEPSEEK_TOKENS_PER_MINUTE")
    groq_requests_per_day: int = Field(default=950, alias="GROQ_REQUESTS_PER_DAY")
    groq_tokens_per_day: int = Field(default=0, alias="GROQ_TOKENS_PER_DAY")
    deepseek_requests_per_day: int = Field(default=0, alias="DEEPSEEK_REQUESTS_PER_DAY")
    deepseek_tokens_per_day: int = Field(default=0, alias="DEEPSEEK_TOKENS_PER_DAY")

    memory_embedding_dimensions: int = Field(default=384, alias="MEMORY_EMBEDDING_DIMENSIONS")
    memory_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="MEMORY_EMBEDDING_MODEL",
    )
    memory_recall_limit: int = Field(default=4, alias="MEMORY_RECALL_LIMIT")
    memory_max_turns_per_session: int = Field(default=300, alias="MEMORY_MAX_TURNS_PER_SESSION")
    memory_vector_index_name: str = Field(default="chat_vectors_index", alias="MEMORY_VECTOR_INDEX_NAME")

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
    def groq_slots(self) -> list[dict[str, str | int]]:
        slots: list[dict[str, str | int]] = []
        for index in range(1, 11):
            key = getattr(self, f"groq_api_key_{index}", None)
            model = getattr(self, f"groq_model_{index}", None) or self.groq_model
            normalized_key = key.strip() if key else ""
            lowered_key = normalized_key.lower()
            if (
                not normalized_key
                or "your" in lowered_key
                or "replace" in lowered_key
                or not normalized_key.startswith("gsk_")
            ):
                continue
            slots.append({"slot": index, "api_key": normalized_key, "model": model})

        fallback_key = self.groq_api_key.strip() if self.groq_api_key else ""
        if fallback_key and not slots and fallback_key.startswith("gsk_"):
            slots.append({"slot": 1, "api_key": fallback_key, "model": self.groq_model})
        return slots

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()