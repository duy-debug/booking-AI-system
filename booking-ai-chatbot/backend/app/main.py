from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from app.api.audio import router as audio_router
from app.api.chat import legacy_router
from app.api.chat import router as chat_router
from app.api.schemas import ApplicationInfoResponse, HealthResponse
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.middleware import CorrelationIdMiddleware, RateLimitMiddleware
from app.integrations import booking_api, qdrant
from app.integrations.redis import close_redis, get_conversation_store
from app.rag.embeddings import _get_model
from app.rag.router import router as knowledge_router

logger = logging.getLogger(__name__)


async def _check_qdrant() -> bool:
    client = await qdrant.get_qdrant()
    await client.get_collections()
    return True


# Quản lý connection pool của các adapter bên ngoài theo vòng đời FastAPI.
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await booking_api.init_client()
    await qdrant.init_qdrant()
    yield
    await booking_api.close_client()
    await qdrant.close_qdrant()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)


# Chuyển AppError thành RFC 9457 Problem Details nhất quán cho client.
@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


# Chuẩn hóa lỗi Pydantic để frontend không phụ thuộc format nội bộ của FastAPI.
@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "detail": "Dữ liệu đầu vào không hợp lệ.",
            "code": "VALIDATION_ERROR",
            "errors": errors,
        },
    )


@app.exception_handler(RedisError)
async def handle_redis_error(_request: Request, _exc: RedisError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "type": "about:blank",
            "title": "Conversation Store Unavailable",
            "status": 503,
            "detail": "Kho trạng thái hội thoại đang tạm thời không khả dụng.",
            "code": "CONVERSATION_STORE_UNAVAILABLE",
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled chatbot error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Hệ thống gặp lỗi không mong đợi.",
            "code": "INTERNAL_ERROR",
        },
    )


app.include_router(chat_router)
app.include_router(legacy_router)
app.include_router(audio_router)
app.include_router(knowledge_router)


# Cung cấp thông tin tối thiểu để xác nhận đúng service đang chạy.
@app.get("/", response_model=ApplicationInfoResponse)
async def root() -> ApplicationInfoResponse:
    return ApplicationInfoResponse(message=settings.APP_NAME)


# Health endpoint không gọi dependency ngoài để dùng được cho container liveness probe.
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready")
async def ready() -> JSONResponse:
    dependencies: dict[str, str] = {}
    checks = await asyncio.gather(
        get_conversation_store().ping(),
        _check_qdrant(),
        booking_api.health(),
        asyncio.to_thread(_get_model),
        return_exceptions=True,
    )
    names = ("redis", "qdrant", "booking_api", "embedding_model")
    for name, result in zip(names, checks, strict=True):
        dependencies[name] = "error" if isinstance(result, Exception) else "ok"
    dependencies["groq_config"] = "ok" if settings.GROQ_API_KEY else "error"
    is_ready = all(value == "ok" for value in dependencies.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "dependencies": dependencies,
        },
    )
