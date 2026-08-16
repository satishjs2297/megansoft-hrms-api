from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class AssessmentRecord(Base):
    __tablename__ = "candidate_assessment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_name = Column(String, nullable=False)
    panel_name = Column(String, nullable=False)
    date_of_interview = Column(String, nullable=False)
    assessment_status = Column(String, nullable=False)
    skills_assessment = Column(Text, nullable=False)
    overall_observation = Column(Text)
    job_description_text = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuthSession(Base):
    __tablename__ = "auth_session"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=False, default="unknown")
    user_agent = Column(String, nullable=True)
    refresh_token_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String, nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    id = Column(Integer, primary_key=True, autoincrement=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    request_hash = Column(String, nullable=False)
    response_json = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False, default=200)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)


def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
