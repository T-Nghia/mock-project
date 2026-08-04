"""
Seed a default Admin account so you can log in immediately after `docker
compose up`. Run with:  docker compose exec backend python -m app.seed
"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole

DEFAULT_ADMIN_EMAIL = "admin@slrms.com"
DEFAULT_ADMIN_PASSWORD = "Admin@123"

def run():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
        if existing:
            print("Admin account already exists.")
            return
        admin = User(
            full_name="System Admin",
            email=DEFAULT_ADMIN_EMAIL,
            hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        print(f"Created admin: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()