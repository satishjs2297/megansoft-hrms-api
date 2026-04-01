import json
from sqlalchemy.orm import Session
from app.database import AssessmentRecord
from app.assessment.schemas import AssessmentCreate


def create_assessment(db: Session, data: AssessmentCreate) -> AssessmentRecord:
    record = AssessmentRecord(
        candidate_name=data.candidate_name,
        panel_name=data.panel_name,
        date_of_interview=data.date_of_interview,
        assessment_status=data.assessment_status,
        skills_assessment=json.dumps(data.skills_assessment),
        overall_observation=data.overall_observation,
        job_description_text=data.job_description_text,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _deserialize(record)


def get_all_assessments(db: Session, search: str = "") -> list:
    query = db.query(AssessmentRecord).order_by(AssessmentRecord.created_at.desc())
    results = query.all()
    records = [_deserialize(r) for r in results]
    if search:
        q = search.lower()
        records = [r for r in records if q in r["candidate_name"].lower() or q in r["panel_name"].lower()]
    return records


def get_assessment_by_id(db: Session, assessment_id: int) -> dict:
    record = db.query(AssessmentRecord).filter(AssessmentRecord.id == assessment_id).first()
    if not record:
        return None
    return _deserialize(record)


def delete_assessment(db: Session, assessment_id: int) -> bool:
    record = db.query(AssessmentRecord).filter(AssessmentRecord.id == assessment_id).first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def _deserialize(record: AssessmentRecord) -> dict:
    d = {
        "id": record.id,
        "candidate_name": record.candidate_name,
        "panel_name": record.panel_name,
        "date_of_interview": record.date_of_interview,
        "assessment_status": record.assessment_status,
        "skills_assessment": json.loads(record.skills_assessment) if isinstance(record.skills_assessment, str) else record.skills_assessment,
        "overall_observation": record.overall_observation,
        "job_description_text": record.job_description_text,
        "created_at": record.created_at,
    }
    return d
