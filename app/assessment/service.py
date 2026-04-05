import json
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import AssessmentRecord, IdempotencyRecord
from app.assessment.schemas import AssessmentCreate

settings = get_settings()


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


def save_idempotent_response(
    db: Session,
    idempotency_key: str,
    request_hash: str,
    response_payload: dict,
    status_code: int = 200,
) -> None:
    existing = db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == idempotency_key).first()
    if existing:
        existing.request_hash = request_hash
        existing.response_json = json.dumps(response_payload, default=str)
        existing.status_code = status_code
        existing.expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.idempotency_ttl_minutes)
    else:
        db.add(
            IdempotencyRecord(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_json=json.dumps(response_payload, default=str),
                status_code=status_code,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.idempotency_ttl_minutes),
            )
        )
    db.commit()


def get_idempotent_response(db: Session, idempotency_key: str) -> IdempotencyRecord | None:
    record = db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == idempotency_key).first()
    if not record:
        return None
    if record.expires_at < datetime.now(timezone.utc):
        db.delete(record)
        db.commit()
        return None
    return record


def compute_request_hash(data: AssessmentCreate) -> str:
    payload = data.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_all_assessments(
    db: Session,
    search: str = "",
    panel_name: str = "",
    feedback_status: str = "",
    date_from: str = "",
    date_to: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list:
    sort_key = (sort_by or "created_at").strip().lower()
    sort_dir = (sort_order or "desc").strip().lower()
    if sort_key not in {"created_at", "date_of_interview", "candidate_name", "panel_name", "assessment_status"}:
        sort_key = "created_at"

    sort_col = getattr(AssessmentRecord, sort_key)
    if sort_dir == "asc":
        query = db.query(AssessmentRecord).order_by(sort_col.asc())
    else:
        query = db.query(AssessmentRecord).order_by(sort_col.desc())
    results = query.all()
    records = [_deserialize(r) for r in results]

    if search:
        q = search.lower()
        records = [r for r in records if q in r["candidate_name"].lower() or q in r["panel_name"].lower()]

    if panel_name:
        panel_query = panel_name.lower()
        records = [r for r in records if panel_query in r["panel_name"].lower()]

    if feedback_status:
        status_query = feedback_status.lower()
        records = [r for r in records if r["assessment_status"].lower() == status_query]

    if date_from:
        from_date = _safe_parse_date(date_from)
        if from_date:
            records = [r for r in records if _record_date_in_range(r["date_of_interview"], from_date, None)]

    if date_to:
        to_date = _safe_parse_date(date_to)
        if to_date:
            records = [r for r in records if _record_date_in_range(r["date_of_interview"], None, to_date)]

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


def _safe_parse_date(value: str):
    if not value:
        return None
    raw = str(value).strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _record_date_in_range(raw_date: str, from_date=None, to_date=None) -> bool:
    parsed = _safe_parse_date(raw_date)
    if not parsed:
        return False
    if from_date and parsed < from_date:
        return False
    if to_date and parsed > to_date:
        return False
    return True
