"""Rollout gates cover the ASGI application, including a legacy DELETE route."""
import re
from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.core.config import settings
from app.storage_certification import require_certificate


def require_document_delete() -> None:
    if not settings.DOCUMENT_DELETE_ENABLED:
        raise HTTPException(status_code=503, detail="Document deletion is under maintenance")
    try:
        require_certificate()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Document deletion target is not certified") from exc


class DocumentMaintenanceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/documents/"):
            method = scope["method"]
            try:
                if method not in {"GET", "HEAD", "OPTIONS"} and not settings.DOCUMENT_MUTATIONS_ENABLED:
                    raise HTTPException(status_code=503, detail="Document mutations are under maintenance")
                if method == "DELETE" and re.fullmatch(r"/documents/[^/]+/?", scope["path"]):
                    require_document_delete()
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=503,
                                        headers={"Retry-After": str(settings.DOCUMENT_DELETE_RETRY_AFTER_SECONDS)})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
