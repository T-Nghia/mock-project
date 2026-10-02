from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="", tags=["Dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    response_model_exclude_none=True,
)
def get_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DashboardService(db).get_dashboard(current_user)
