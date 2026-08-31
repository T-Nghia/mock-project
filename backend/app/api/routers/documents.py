import uuid
from urllib.parse import quote
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission
from app.core.security import require_permission
from app.models.document import ProcessingStatus
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.user_repo import UserRepository
from app.schemas.document import DocumentMetadataResponse, DocumentResponse
from app.services.document_service import DocumentService
from app.services.document_dispatcher import dispatch_document_processing

router = APIRouter(prefix="", tags=["Documents"])


def _build_service(db: Session) -> DocumentService:
    return DocumentService(
        doc_repo=DocumentRepository(db),
        tag_repo=TagRepository(db),
        user_repo=UserRepository(db),
    )


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
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
    service = _build_service(db)

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
    dispatch_document_processing(
        service=service,
        document_id=document.id,
        background_tasks=background_tasks,
    )

    return document


@router.post("/documents/{document_id}/retry", response_model=DocumentResponse)
def retry_document_endpoint(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permission(Permission.REVIEW_DOCUMENT)),
    db: Session = Depends(get_db),
):
    service = _build_service(db)
    document = service._get_document_or_404(document_id)
    role = getattr(current_user.role, "value", current_user.role)
    if document.uploaded_by != current_user.id and role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen retry")
    if document.processing_status not in {ProcessingStatus.FAILED, ProcessingStatus.PENDING}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document cannot be retried")
    service.doc_repo.update_status(document, ProcessingStatus.PENDING)
    dispatch_document_processing(
        service=service, document_id=document.id, background_tasks=background_tasks
    )
    return document


@router.get(
    "/documents/{document_id}",
    response_model=DocumentMetadataResponse,
)
def get_document_metadata_endpoint(
    document_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.READ_DOCUMENT)),
    db: Session = Depends(get_db),
):
    """Xem thông tin chi tiết tài liệu.

    Trả về: người upload, ngày tạo, dung lượng, loại file, trạng thái xử lý AI, tags.
    """
    service = _build_service(db)
    return service.get_metadata(document_id)


@router.get("/documents/{document_id}/download")
def download_document_endpoint(
    document_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.READ_DOCUMENT)),
    db: Session = Depends(get_db),
):
    """Tải tài liệu về máy.

    Cho phép Student/Teacher (và Admin, vì Admin có mọi quyền) — đúng với
    Actor "Student, Teacher" quy định trong đặc tả.
    """
    service = _build_service(db)
    content, download_name, media_type = service.get_file_for_download(document_id)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(download_name)}"},
    )


@router.get("/documents/{document_id}/view")
def view_document_endpoint(
    document_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.READ_DOCUMENT)),
    db: Session = Depends(get_db),
):
    """Xem tài liệu trực tiếp trên trình duyệt (inline), không ép tải về máy.

    Dùng cho preview: nhúng PDF/ảnh trong <iframe>/<img> ngay trên web thay vì
    phải tải file xuống trước như endpoint /download.
    """
    service = _build_service(db)
    content, display_name, media_type = service.get_file_for_view(document_id)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename*=utf-8''{quote(display_name)}"},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_endpoint(
    document_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.REVIEW_DOCUMENT)),
    db: Session = Depends(get_db),
):
    """Xóa tài liệu.

    Chỉ người đã tải tài liệu lên hoặc Admin mới được xóa. Student không có
    quyền REVIEW_DOCUMENT nên không thể gọi endpoint này.
    """
    service = _build_service(db)
    service.delete_document(document_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
