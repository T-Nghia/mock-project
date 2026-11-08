"""Register all models for Alembic and metadata-based test databases."""

from app.models import (  # noqa: F401
    chat, document, folder, password_reset_token, social, storage_cleanup, tag, user,
)
