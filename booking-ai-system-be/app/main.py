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
from app.api.public.therapist_schedule import router as therapist_schedule_router
from app.api.admin.bookings import router as admin_bookings_router
from app.api.public.auth import router as auth_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Exception handlers — RFC 9457 Problem Details cho toàn bộ API


@app.exception_handler(RequestValidationError)
def validation_handler(request: Request, exc: RequestValidationError):
    """FastAPI validation error → RFC 9457 format"""
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


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    """AppError / HTTPException → RFC 9457 Problem Details (unwrap detail dict)"""
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
app.include_router(therapist_schedule_router)
app.include_router(admin_bookings_router)
app.include_router(auth_router)


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} v{settings.APP_VERSION}"}


@app.get("/health")
def health():
    return {"status": "ok"}
