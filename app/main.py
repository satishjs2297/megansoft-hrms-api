import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import create_tables
from app.config import get_settings
from app.auth.router import router as auth_router
from app.resume.router import router as resume_router
from app.assessment.router import router as assessment_router
from app.reports.router import router as reports_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    os.makedirs(settings.resolved_output_dir, exist_ok=True)
    os.makedirs(settings.resolved_templates_dir, exist_ok=True)
    yield

app = FastAPI(title="MeganSoft HRMS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(resume_router, prefix="/resume", tags=["resume"])
app.include_router(assessment_router, prefix="/assessment", tags=["assessment"])
app.include_router(reports_router, prefix="/reports", tags=["reports"])

@app.get("/health")
def health():
    return {"status": "ok"}
