import math
import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.folder import Folder
from app.models.social import Bookmark
from app.models.tag import Tag, DocumentTag
from app.schemas.search import DocumentSearchResult, SearchPaginatedResponse
from app.utils.text_extract import embed_text


class SearchRepository:

    def __init__(self, db: Session):
        self.db = db

    def search_documents(
        self,
        *,
        user_id: uuid.UUID,
        keyword: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        subject: str | None = None,
        folder_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchPaginatedResponse:
        # Base query selecting distinct document IDs
        stmt = (
            select(Document.id)
            .outerjoin(Folder, Document.folder_id == Folder.id)
            .outerjoin(DocumentTag, Document.id == DocumentTag.document_id)
            .outerjoin(Tag, DocumentTag.tag_id == Tag.id)
        )

        filters = []

        # 0. Enforce Permission & Bookmark Filter (Owned documents OR Bookmarked documents)
        bookmarked_subquery = (
            select(Bookmark.document_id).where(Bookmark.user_id == user_id)
        )
        permission_filter = or_(
            Document.uploaded_by == user_id,
            Document.id.in_(bookmarked_subquery),
        )
        filters.append(permission_filter)

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

        # Handle Keyword Search with Adaptive RankCut & Dual-Path RRF Fusion
        if keyword and keyword.strip():
            k = keyword.strip()
            is_postgres = bool(self.db.bind and self.db.bind.dialect.name == "postgresql")

            # Wildcard pattern to handle glued PDF words (e.g. "vận trùhọc" vs "vận trù học")
            k_tokens = k.split()
            k_wildcard = "%" + "%".join(k_tokens) + "%" if len(k_tokens) > 1 else f"%{k}%"

            # Path A (Sparse Keyword Ranks): Find doc IDs matching keyword in Title, Tag, Subject, or PDF Chunk Text
            chunk_text_doc_ids = (
                select(DocumentChunk.document_id)
                .where(
                    or_(
                        DocumentChunk.content.ilike(f"%{k}%"),
                        DocumentChunk.content.ilike(k_wildcard),
                    )
                )
            )
            keyword_match_filter = or_(
                Document.title.ilike(f"%{k}%"),
                Document.title.ilike(k_wildcard),
                Tag.name.ilike(f"%{k}%"),
                Folder.subject.ilike(f"%{k}%"),
                Document.id.in_(chunk_text_doc_ids),
            )

            # Query Path A doc_ids
            path_a_stmt = (
                select(Document.id)
                .outerjoin(Folder, Document.folder_id == Folder.id)
                .outerjoin(DocumentTag, Document.id == DocumentTag.document_id)
                .outerjoin(Tag, DocumentTag.tag_id == Tag.id)
                .where(permission_filter, keyword_match_filter)
                .distinct()
                .limit(50)
            )
            path_a_doc_ids = [r[0] for r in self.db.execute(path_a_stmt).all()]

            path_b_doc_ids = []
            if is_postgres:
                # Path B (Dense Vector Ranks with Adaptive RankCut / Dynamic Relative Margin Pruning)
                query_embedding = embed_text(k)
                distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")

                path_b_stmt = (
                    select(DocumentChunk.document_id, distance)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        permission_filter,
                        DocumentChunk.embedding.is_not(None),
                        Document.processing_status == ProcessingStatus.DONE,
                    )
                    .order_by(distance.asc())
                    .limit(50)
                )
                path_b_rows = self.db.execute(path_b_stmt).all()

                if path_b_rows:
                    best_dist = float(path_b_rows[0][1])
                    # Adaptive Cutoff: Only retain documents within relative delta margin of best match
                    adaptive_threshold = min(best_dist + 0.06, 0.75)

                    seen_b = set()
                    for doc_id, dist_val in path_b_rows:
                        if float(dist_val) <= adaptive_threshold and doc_id not in seen_b:
                            seen_b.add(doc_id)
                            path_b_doc_ids.append(doc_id)

            # Compute RRF Fusion Scores for candidate document IDs
            rrf_scores: dict[uuid.UUID, float] = {}

            for rank_a, doc_id in enumerate(path_a_doc_ids, start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60.0 + rank_a))

            for rank_b, doc_id in enumerate(path_b_doc_ids, start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60.0 + rank_b))

            if not rrf_scores:
                return SearchPaginatedResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                )

            # Sort candidate document IDs by RRF Score descending
            sorted_candidate_ids = [
                doc_id for doc_id, _ in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
            ]

            # Apply remaining filters (title, subject, folder_id, tags) to sorted candidates
            filters.append(Document.id.in_(sorted_candidate_ids))
            stmt = stmt.where(*filters).distinct()
            subq = stmt.subquery()

            count_stmt = select(func.count()).select_from(subq)
            total_count = self.db.scalar(count_stmt) or 0

            # Filter sorted_candidate_ids to those matching all filters
            filtered_candidate_set = set([r[0] for r in self.db.execute(select(subq.c.id)).all()])
            final_ordered_ids = [doc_id for doc_id in sorted_candidate_ids if doc_id in filtered_candidate_set]

            offset = (page - 1) * page_size
            paged_doc_ids = final_ordered_ids[offset : offset + page_size]

        else:
            # Normal SQL Search when no keyword is provided
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.distinct()
            subq = stmt.subquery()

            count_stmt = select(func.count()).select_from(subq)
            total_count = self.db.scalar(count_stmt) or 0

            offset = (page - 1) * page_size
            id_stmt = (
                select(Document.id, Document.created_at)
                .where(Document.id.in_(select(subq.c.id)))
                .order_by(Document.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            id_rows = self.db.execute(id_stmt).all()
            paged_doc_ids = [r[0] for r in id_rows]

        if not paged_doc_ids:
            return SearchPaginatedResponse(
                items=[],
                total=total_count,
                page=page,
                page_size=page_size,
                total_pages=math.ceil(total_count / page_size) if total_count > 0 else 0,
            )

        # Fetch actual Documents with Folder & Tags
        doc_stmt = (
            select(
                Document,
                Folder.name.label("folder_name"),
                Folder.subject.label("folder_subject"),
            )
            .outerjoin(Folder, Document.folder_id == Folder.id)
            .where(Document.id.in_(paged_doc_ids))
        )
        results_rows = self.db.execute(doc_stmt).all()
        doc_map = {row.Document.id: row for row in results_rows}

        tags_by_doc: dict[uuid.UUID, list[str]] = {doc_id: [] for doc_id in paged_doc_ids}
        tag_stmt = (
            select(DocumentTag.document_id, Tag.name)
            .join(Tag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id.in_(paged_doc_ids))
        )
        tag_rows = self.db.execute(tag_stmt).all()
        for doc_id, tag_name in tag_rows:
            tags_by_doc[doc_id].append(tag_name)

        items = []
        for doc_id in paged_doc_ids:
            if doc_id not in doc_map:
                continue
            row = doc_map[doc_id]
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
