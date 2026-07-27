from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.request_context import correlation_id_context
from app.integrations.redis import get_conversation_store


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        try:
            correlation_id = str(UUID(supplied)) if supplied else str(uuid4())
        except ValueError:
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        token = correlation_id_context.set(correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            correlation_id_context.reset(token)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in {"/api/chat", "/api/v1/chat", "/api/kb/seed"}:
            client_ip = request.client.host if request.client else "unknown"
            try:
                allowed = await get_conversation_store().check_rate_limit(
                    f"{request.url.path}:{client_ip}",
                    settings.RATE_LIMIT_REQUESTS,
                    settings.RATE_LIMIT_WINDOW_SECONDS,
                )
            except Exception:
                return JSONResponse(
                    status_code=503,
                    content={
                        "type": "about:blank",
                        "title": "Conversation Store Unavailable",
                        "status": 503,
                        "detail": "Không thể kiểm tra giới hạn yêu cầu.",
                        "code": "CONVERSATION_STORE_UNAVAILABLE",
                    },
                )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "about:blank",
                        "title": "Rate Limit Exceeded",
                        "status": 429,
                        "detail": "Bạn gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
                        "code": "RATE_LIMIT_EXCEEDED",
                    },
                )
        return await call_next(request)
