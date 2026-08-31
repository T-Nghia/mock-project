from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Smart Learning Resource Management System"
    ENV: str = "development"

    DATABASE_URL: str = "postgresql+psycopg2://slrms:slrms_password@db:5432/slrms"
    REDIS_URL: str = "redis://redis:6379/0"
    AUTH_RATE_LIMIT_ENABLED: bool = False
    AUTH_RATE_LIMIT_REQUESTS: int = 10
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60

    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "slrms_refresh_token"
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: str = "lax"
    REFRESH_COOKIE_PATH: str = "/auth"

    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    STORAGE_BACKEND: str = "local"
    STORAGE_BUCKET: str = ""
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_REGION: str = "auto"
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    DOCUMENT_PROCESSING_MODE: str = "background"
    CELERY_BROKER_URL: str = ""
    DOCUMENT_TASK_MAX_RETRIES: int = 5
    DOCUMENT_TASK_TIMEOUT_SECONDS: int = 900

    # Optional: set to enable real LLM-based RAG answers / embedding.
    # When empty, the AI Assistant falls back to a local keyword-search
    # + extractive-summary implementation so the project runs out of the box.
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    GEMINI_TEXT_MODEL: str = ""
    GEMINI_TIMEOUT_SECONDS: float = 30.0
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    GEMINI_EMBEDDING_DIM: int = 384
    GEMINI_EMBEDDING_BATCH_TOKENS: int = 27000
    GEMINI_EMBEDDING_CHUNK_TOKENS: int = 500
    GEMINI_EMBEDDING_CHUNK_OVERLAP_TOKENS: int = 80

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    PASSWORD_RESET_EXPIRE_MINUTES: int = 15
    FRONTEND_URL: str = "http://localhost:3000"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@slrms.local"

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.ENV.lower() != "production":
            return self

        sample_secrets = {
            "change-me-in-env",
            "super-secret-change-me",
            "your-secret-key",
            "secret",
        }
        if self.JWT_SECRET_KEY.strip().lower() in sample_secrets:
            raise ValueError("JWT_SECRET_KEY must not use a sample value in production")
        if len(self.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters in production")
        if bool(self.ADMIN_EMAIL) != bool(self.ADMIN_PASSWORD):
            raise ValueError("ADMIN_EMAIL and ADMIN_PASSWORD must be configured together")
        if self.ADMIN_PASSWORD and len(self.ADMIN_PASSWORD) < 12:
            raise ValueError("ADMIN_PASSWORD must contain at least 12 characters in production")
        if not self.REFRESH_COOKIE_SECURE:
            raise ValueError("REFRESH_COOKIE_SECURE must be enabled in production")
        if self.REFRESH_COOKIE_SAMESITE.lower() != "none":
            raise ValueError("REFRESH_COOKIE_SAMESITE must be 'none' in production")
        if self.DOCUMENT_PROCESSING_MODE.lower() != "celery":
            raise ValueError("DOCUMENT_PROCESSING_MODE must be 'celery' in production")
        if self.STORAGE_BACKEND.lower() != "s3":
            raise ValueError("STORAGE_BACKEND must be 's3' in production")
        if not self.AUTH_RATE_LIMIT_ENABLED:
            raise ValueError("AUTH_RATE_LIMIT_ENABLED must be enabled in production")
        required_storage = {
            "STORAGE_BUCKET": self.STORAGE_BUCKET,
            "STORAGE_ACCESS_KEY_ID": self.STORAGE_ACCESS_KEY_ID,
            "STORAGE_SECRET_ACCESS_KEY": self.STORAGE_SECRET_ACCESS_KEY,
        }
        missing = [name for name, value in required_storage.items() if not value]
        if missing:
            raise ValueError(f"Missing production object storage settings: {', '.join(missing)}")
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
