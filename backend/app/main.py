from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app import models
from app.api.routes.auth import router as auth_router

<<<<<<< HEAD
=======
#from app.api.routers import auth
>>>>>>> 46708e2193133e10a42c066d1d34aae07f563368

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

# Schema management (CREATE EXTENSION vector + all tables) is handled by
# Alembic migrations now, run automatically before the API starts — see
# the `backend` service command in docker-compose.yml and alembic/env.py.


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}
