import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, ProcessingStatus
from app.utils.text_extract import extract_text, make_summary

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}

def upload_document(db: Session, user_id: str, file: UploadFile, title: str | None = None):
    ext = Path(file.filename or "").suffix.lower().lstrip(".")

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Loại file không hỗ trợ")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = upload_dir / stored_name

    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File quá lớn")

    with file_path.open("wb") as f:
        f.write(content)

    text = extract_text(str(file_path), ext)
    summary = make_summary(text)

    doc = Document(
        title=title or (file.filename or "Untitled Document"),
        file_path=str(file_path),
        file_type=ext,
        uploaded_by=user_id,
        summary=summary,
        processing_status=ProcessingStatus.DONE,
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc