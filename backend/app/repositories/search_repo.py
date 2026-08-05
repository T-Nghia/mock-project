import math
import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.folder import Folder
from app.models.tag import Tag, DocumentTag
from app.schemas.search import DocumentSearchResult, SearchPaginatedResponse


class SearchRepository:

    def __init__(self, db: Session):
        self.db = db

    def search_documents(
        self,
        keyword: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        subject: str | None = None,
        folder_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchPaginatedResponse:
        stmt = (
            select(
                Document,
                Folder.name.label("folder_name"),
                Folder.subject.label("folder_subject"),
            )
            .outerjoin(Folder, Document.folder_id == Folder.id)
            .outerjoin(DocumentTag, Document.id == DocumentTag.document_id)
            .outerjoin(Tag, DocumentTag.tag_id == Tag.id)
        )

        filters = []

        # 1. Unified Search Keyword (OR condition across Title, Tag Name, Subject)
        if keyword and keyword.strip():
            k = keyword.strip()
            filters.append(
                or_(
                    Document.title.ilike(f"%{k}%"),
                    Tag.name.ilike(f"%{k}%"),
                    Folder.subject.ilike(f"%{k}%"),
                )
            )

        # 2. Filter specifically by Document Title
        if title and title.strip():
            clean_title = title.strip()
            filters.append(Document.title.ilike(f"%{clean_title}%"))

        # 3. Filter specifically by Folder Subject
        if subject and subject.strip():
            clean_subject = subject.strip()
            filters.append(Folder.subject.ilike(f"%{clean_subject}%"))

        # 4. Filter specifically by Folder ID
        if folder_id:
            filters.append(Document.folder_id == folder_id)

        # 5. Filter specifically by Tag Names
        if tags and len(tags) > 0:
            clean_tags = [t.strip() for t in tags if t.strip()]
            if clean_tags:
                tag_conditions = [Tag.name.ilike(f"%{t}%") for t in clean_tags]
                filters.append(or_(*tag_conditions))

        if filters:
            stmt = stmt.where(*filters)

        stmt = stmt.distinct()

        subq = stmt.subquery()
        count_stmt = select(func.count()).select_from(subq)
        total_count = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Document.created_at.desc()).offset(offset).limit(page_size)

        results = self.db.execute(stmt).all()

        doc_ids = [row.Document.id for row in results]
        tags_by_doc: dict[uuid.UUID, list[str]] = {doc_id: [] for doc_id in doc_ids}

        if doc_ids:
            tag_stmt = (
                select(DocumentTag.document_id, Tag.name)
                .join(Tag, DocumentTag.tag_id == Tag.id)
                .where(DocumentTag.document_id.in_(doc_ids))
            )
            tag_rows = self.db.execute(tag_stmt).all()
            for doc_id, tag_name in tag_rows:
                tags_by_doc[doc_id].append(tag_name)

        items = []
        for row in results:
            doc: Document = row.Document
            folder_name: str | None = row.folder_name
            folder_subject: str | None = row.folder_subject

            item = DocumentSearchResult(
                id=doc.id,
                title=doc.title,
                file_type=doc.file_type,
                summary=doc.summary,
                folder_id=doc.folder_id,
                folder_name=folder_name,
                subject=folder_subject,
                tags=tags_by_doc.get(doc.id, []),
                uploaded_by=doc.uploaded_by,
                created_at=doc.created_at,
            )
            items.append(item)

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        return SearchPaginatedResponse(
            items=items,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
