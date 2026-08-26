"""
Optionally seed an Admin account from environment variables.
"""
from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User, UserRole

def run():
    if not settings.ADMIN_EMAIL and not settings.ADMIN_PASSWORD:
        print("ADMIN_EMAIL/ADMIN_PASSWORD are not set; skipping Admin seed.")
        return
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must be configured together")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if existing:
            print("Admin account already exists.")
            return
        admin = User(
            full_name="System Admin",
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        print(f"Created admin: {settings.ADMIN_EMAIL}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
