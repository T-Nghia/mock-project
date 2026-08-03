import uuid
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email.strip().lower()).first()

    def list_all(self) -> list[User]:
        return self.db.query(User).order_by(User.created_at.desc()).all()

    def update_role(self, user: User, role: UserRole) -> User:
        user.role = role
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_active_status(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        self.db.commit()
        self.db.refresh(user)
        return user

    def create(
        self, 
        full_name: str, 
        email: str, 
        hashed_password: str, 
        role: UserRole = UserRole.STUDENT
    ) -> User:
        user = User(
            full_name=full_name.strip(),
            email=email.strip().lower(),
            hashed_password=hashed_password,
            role=role,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
