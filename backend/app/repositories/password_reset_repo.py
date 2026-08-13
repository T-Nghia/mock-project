import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken


class PasswordResetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> PasswordResetToken:
        row = PasswordResetToken(user_id = user_id, token_hash = token_hash, expires_at = expires_at)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_used(self, row: PasswordResetToken) -> None:
        row.used_at = datetime.now(timezone.utc)
        self.db.commit()

    def get_valid_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None or row.used_at is not None:
            return None
        if row.expires_at < datetime.now(timezone.utc):
            return None
        return row

    def invalidate_all_for_user(self, user_id: uuid.UUID) -> None:
        """Vô hiệu hóa các token cũ chưa dùng khi user xin link reset mới,
        đảm bảo chỉ link mới nhất còn hiệu lực."""
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        now = datetime.now(timezone.utc)
        for row in self.db.execute(stmt).scalars().all():
            row.used_at = now
        self.db.commit()