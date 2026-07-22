# FastAPI app entry — điểm khởi chạy backend

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.admin.shops import router as admin_shops_router
from app.api.admin.courses import router as admin_courses_router
from app.api.admin.therapists import router as admin_therapists_router
from app.api.admin.therapist_shifts import router as admin_shifts_router
from app.api.admin.customer_restrictions import router as admin_restrictions_router
from app.api.public.shops import router as public_shops_router
from app.api.public.available_slots import router as public_slots_router
from app.api.public.booking_eligibility import router as public_eligibility_router
from app.api.public.bookings import router as public_bookings_router
from app.api.public.therapist_booking import router as therapist_booking_router
from app.api.admin.bookings import router as admin_bookings_router
from app.api.admin.booking import router as admin_booking_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Exception handlers — RFC 9457 Problem Details cho toàn bộ API


# Chuyển lỗi kiểm tra dữ liệu đầu vào của FastAPI sang cấu trúc Problem Details thống nhất cho frontend.
@app.exception_handler(RequestValidationError)
def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "detail": "One or more fields are invalid.",
            "code": "VALIDATION_ERROR",
            "instance": str(request.url.path),
            "errors": [
                {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
                for err in exc.errors()
            ],
        },
    )


# Chuẩn hóa AppError và HTTPException thành response RFC 9457, đồng thời giữ nguyên mã lỗi nghiệp vụ.
@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": "Error",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "code": "UNKNOWN_ERROR",
            "instance": str(request.url.path),
        },
    )


# CORS — cho phép frontend gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin routers
app.include_router(admin_shops_router)
app.include_router(admin_courses_router)
app.include_router(admin_therapists_router)
app.include_router(admin_shifts_router)
app.include_router(admin_restrictions_router)

# Public routers
app.include_router(public_shops_router)
app.include_router(public_slots_router)
app.include_router(public_eligibility_router)
app.include_router(public_bookings_router)
app.include_router(therapist_booking_router)
app.include_router(admin_bookings_router)
app.include_router(admin_booking_router)


# Trả về tên và phiên bản ứng dụng để xác nhận nhanh backend đang hoạt động.
@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} v{settings.APP_VERSION}"}


# Cung cấp endpoint health-check tối giản cho Docker, CI hoặc hệ thống giám sát.
@app.get("/health")
def health():
    return {"status": "ok"}
