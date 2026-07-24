from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.schemas import ApplicationInfoResponse, HealthResponse
from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations import booking_api, qdrant
from app.integrations.redis import close_redis
from app.rag.router import router as knowledge_router


# Quản lý connection pool của các adapter bên ngoài theo vòng đời FastAPI.
@asynccontextmanager
async def lifespan(_app: FastAPI):
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


app.include_router(chat_router)
app.include_router(knowledge_router)


# Cung cấp thông tin tối thiểu để xác nhận đúng service đang chạy.
@app.get("/", response_model=ApplicationInfoResponse)
async def root() -> ApplicationInfoResponse:
    return ApplicationInfoResponse(message=settings.APP_NAME)


# Health endpoint không gọi dependency ngoài để dùng được cho container liveness probe.
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
