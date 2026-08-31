import hashlib

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis_client import redis_client


def auth_rate_limit(scope: str):
    """Return a Redis fixed-window limiter dependency for sensitive auth routes."""

    def check(request: Request) -> None:
        if not settings.AUTH_RATE_LIMIT_ENABLED or settings.ENV.lower() == "test":
            return
        client = request.client.host if request.client else "unknown"
        identity = hashlib.sha256(client.encode()).hexdigest()[:24]
        key = f"rate-limit:auth:{scope}:{identity}"
        try:
            with redis_client.pipeline() as pipe:
                pipe.incr(key)
                pipe.ttl(key)
                count, ttl = pipe.execute()
                if ttl < 0:
                    redis_client.expire(key, settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
                    ttl = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS
        except RedisError as exc:
            if settings.ENV.lower() == "production":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication protection is temporarily unavailable",
                ) from exc
            return
        if count > settings.AUTH_RATE_LIMIT_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts",
                headers={"Retry-After": str(max(ttl, 1))},
            )

    return check
