from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.repositories.dashboard_repo import DashboardRepository
from app.schemas.dashboard import (
    ChartPoint,
    DashboardCharts,
    DashboardResponse,
    DashboardSummary,
    UploadChartPoint,
)


class DashboardService:
    def __init__(self, db: Session):
        self.repo = DashboardRepository(db)

    def get_dashboard(self, current_user: User) -> DashboardResponse:
        role = getattr(current_user.role, "value", current_user.role)
        if role == UserRole.STUDENT.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dashboard is not available for students.",
            )

        if role == UserRole.ADMIN.value:
            return self._build_dashboard(role, owner_id=None, include_users=True)

        if role == UserRole.TEACHER.value:
            return self._build_dashboard(
                role, owner_id=current_user.id, include_users=False
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dashboard is not available for this role.",
        )

    def _build_dashboard(self, role: str, owner_id, include_users: bool) -> DashboardResponse:
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=6)
        upload_counts = self.repo.uploads_by_day(owner_id, start_date, end_date)
        uploads_by_day = [
            UploadChartPoint(
                date=(start_date + timedelta(days=offset)).isoformat(),
                count=upload_counts.get(start_date + timedelta(days=offset), 0),
            )
            for offset in range(7)
        ]
        documents_by_folder = [
            ChartPoint(label=label, count=count)
            for label, count in self.repo.documents_by_folder(owner_id)
        ]

        summary = DashboardSummary(
            total_documents=self.repo.count_documents(owner_id),
            total_users=self.repo.count_users() if include_users else None,
        )
        charts = DashboardCharts(
            uploads_by_day=uploads_by_day,
            documents_by_folder=documents_by_folder,
            users_by_role=(
                [
                    ChartPoint(label=label, count=count)
                    for label, count in self.repo.users_by_role()
                ]
                if include_users
                else None
            ),
        )
        return DashboardResponse(role=role, summary=summary, charts=charts)
