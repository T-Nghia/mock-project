from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import require_permission
from app.services.document import upload_document

router = APIRouter(prefix="", tags=["Documents"])


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
def upload_document_endpoint(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    folder_id: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    current_user=Depends(require_permission(Permission.CREATE_DOCUMENT)),
    db: Session = Depends(get_db),
):
    return upload_document(
        db=db,
        user_id=str(current_user.id),
        file=file,
        title=title,
        folder_id=folder_id,
        tags=tags,
    )
