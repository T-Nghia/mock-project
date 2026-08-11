from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_documents: int
    total_users: int | None = None


class ChartPoint(BaseModel):
    label: str
    count: int


class UploadChartPoint(BaseModel):
    date: str
    count: int


class DashboardCharts(BaseModel):
    uploads_by_day: list[UploadChartPoint]
    documents_by_folder: list[ChartPoint]
    users_by_role: list[ChartPoint] | None = None


class DashboardResponse(BaseModel):
    role: str
    summary: DashboardSummary
    charts: DashboardCharts
