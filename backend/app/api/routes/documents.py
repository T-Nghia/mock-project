from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.document import upload_document
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),  # cần thêm dependency auth
):
    doc = upload_document(db, str(current_user.id), file, title=title)
    return {
        "message": "Upload thành công",
        "document_id": str(doc.id),
        "title": doc.title,
        "file_type": doc.file_type,
        "summary": doc.summary,
    }
