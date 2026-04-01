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

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
