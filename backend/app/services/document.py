import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, ProcessingStatus
from app.models.tag import DocumentTag
from app.repositories.tag import create_tag, get_tag_by_name
from app.utils.text_extract import extract_text, make_summary

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "pptx", "jpg", "jpeg"}


def upload_document(
    db: Session,
    user_id: str,
    file: UploadFile,
    title: str | None = None,
    folder_id: str | None = None,
    tags: str | None = None,
):
    ext = Path(file.filename or "").suffix.lower().lstrip(".")

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Loại file không hỗ trợ")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = upload_dir / stored_name

    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File quá lớn")

    with file_path.open("wb") as f:
        f.write(content)

    text = extract_text(str(file_path), ext)
    summary = make_summary(text)

    doc = Document(
        title=title or (file.filename or "Untitled Document"),
        file_path=str(file_path),
        file_type=ext,
        folder_id=folder_id,
        uploaded_by=user_id,
        summary=summary,
        processing_status=ProcessingStatus.DONE,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]
        for tag_name in parsed_tags:
            tag = get_tag_by_name(db, tag_name)
            if tag is None:
                tag = create_tag(db, tag_name)

            association = DocumentTag(document_id=doc.id, tag_id=tag.id)
            db.add(association)

        db.commit()

    return doc
