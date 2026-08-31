from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.redis_client import redis_client
from app import models  # noqa: F401 - register SQLAlchemy models
from app.api.routers.auth import router as auth_router
from app.api.routers.documents import router as documents_router
from app.api.routers.folders import router as folders_router
from app.api.routers.search import router as search_router
from app.api.routers.social import router as social_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.chat import router as chat_router


app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(folders_router)
app.include_router(social_router)
app.include_router(search_router)
app.include_router(dashboard_router)
app.include_router(chat_router)

# Schema management (CREATE EXTENSION vector + all tables) is handled by
# Alembic migrations now, run automatically before the API starts — see
# the `backend` service command in docker-compose.yml and alembic/env.py.


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok"}


@app.get("/health")
@app.get("/health/live")
def health():
    return {"status": "healthy"}


@app.get("/health/ready")
def readiness():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        redis_client.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Dependencies are not ready") from exc
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    from sqlalchemy import func, select
    from app.models.document import Document

    with SessionLocal() as db:
        rows = db.execute(
            select(Document.processing_status, func.count(Document.id)).group_by(
                Document.processing_status
            )
        ).all()
    lines = [
        "# HELP slrms_documents_total Documents by processing status",
        "# TYPE slrms_documents_total gauge",
    ]
    lines.extend(
        f'slrms_documents_total{{status="{getattr(state, "value", state)}"}} {count}'
        for state, count in rows
    )
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


