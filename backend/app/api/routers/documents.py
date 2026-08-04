import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import require_permission
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.services.document_service import DocumentService

router = APIRouter(prefix="", tags=["Documents"])


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
def upload_document_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    folder_id: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    current_user=Depends(require_permission(Permission.CREATE_DOCUMENT)),
    db: Session = Depends(get_db),
):
    # 1. Khởi tạo Repository và Service
    doc_repo = DocumentRepository(db)
    tag_repo = TagRepository(db)
    service = DocumentService(doc_repo=doc_repo, tag_repo=tag_repo)

    # 2. Xử lý các tham số đầu vào
    # Convert string uuid từ Form sang object uuid.UUID
    parsed_folder_id = uuid.UUID(folder_id) if folder_id else None
    
    # Tach chuoi tags "tag1, tag2" thanh list ["tag1", "tag2"]
    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    # 3. Lưu file & tạo Document record (Trạng thái PENDING - Trả kết quả ngay)
    document = service.save_upload(
        file=file,
        title=title,
        folder_id=parsed_folder_id,
        uploaded_by=current_user.id,
        tags=parsed_tags,
    )

    # 4. Đẩy công việc nặng (Extract text, Chunking, Embedding) vào Background Task
    background_tasks.add_task(service.process_document_sync, document.id)

    return document