import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from app.assessment.router import router as assessment_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.database import create_tables
from app.reports.router import router as reports_router
from app.resume.router import router as resume_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    os.makedirs(settings.resolved_output_dir, exist_ok=True)
    os.makedirs(settings.resolved_templates_dir, exist_ok=True)
    yield


app = FastAPI(title="MeganSoft HRMS API", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "Content-Disposition"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started_at = datetime.utcnow()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
    print(f"[req] id={request_id} method={request.method} path={request.url.path} status={response.status_code} ms={elapsed_ms}")
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    payload = {
        "code": f"HTTP_{exc.status_code}",
        "message": str(exc.detail),
        "detail": str(exc.detail),  # Backward-compatible key for existing web error parsing.
        "details": {"path": request.url.path, "method": request.method},
        "request_id": request_id,
    }
    return JSONResponse(status_code=exc.status_code, content=payload, headers={"X-Request-Id": request_id or ""})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    payload = {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Unexpected server error",
        "detail": "Unexpected server error",
        "details": {"path": request.url.path, "method": request.method},
        "request_id": request_id,
    }
    print(f"[err] id={request_id} path={request.url.path} error={repr(exc)}")
    return JSONResponse(status_code=500, content=payload, headers={"X-Request-Id": request_id or ""})


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(resume_router, prefix="/resume", tags=["resume"])
app.include_router(assessment_router, prefix="/assessment", tags=["assessment"])
app.include_router(reports_router, prefix="/reports", tags=["reports"])


@app.get("/health")
def health():
    return {"status": "ok"}
