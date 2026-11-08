from sqlalchemy.orm import Session

from app.models.storage_cleanup import StorageCleanupJob


class StorageCleanupJobRepository:
    def __init__(self, db: Session):
        self.db = db

    def stage(self, job: StorageCleanupJob) -> None:
        """Join the deletion transaction; its service owns flush and commit."""
        self.db.add(job)
