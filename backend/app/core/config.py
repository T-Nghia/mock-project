from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Smart Learning Resource Management System"
    ENV: str = "development"

    DATABASE_URL: str = "postgresql+psycopg2://slrms:slrms_password@db:5432/slrms"
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # Optional: set to enable real LLM-based RAG answers / embedding.
    # When empty, the AI Assistant falls back to a local keyword-search
    # + extractive-summary implementation so the project runs out of the box.
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = "" 

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    PASSWORD_RESET_EXPIRE_MINUTES: int = 15
    FRONTEND_URL: str = "http://localhost:3000"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@slrms.local"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
