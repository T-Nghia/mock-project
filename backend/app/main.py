from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app import models
from app.api.routers.auth import router as auth_router
from app.api.routers.documents import router as documents_router
from app.api.routers.folders import router as folders_router
from app.api.routers.search import router as search_router
from app.api.routers.dashboard import router as dashboard_router


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
app.include_router(search_router)
app.include_router(dashboard_router)

# Schema management (CREATE EXTENSION vector + all tables) is handled by
# Alembic migrations now, run automatically before the API starts — see
# the `backend` service command in docker-compose.yml and alembic/env.py.


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


