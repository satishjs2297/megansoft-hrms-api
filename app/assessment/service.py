import json
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import IdempotencyRecord
from app.assessment.gcs_storage import get_assessment_storage
from app.assessment.schemas import AssessmentCreate

settings = get_settings()


def create_assessment(db: Session, data: AssessmentCreate) -> dict:
    payload = data.model_dump(mode="json")
    return get_assessment_storage().create(payload)


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

    records = get_assessment_storage().list()

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

    return _sort_records(records, sort_key, sort_dir)


def get_assessment_by_id(db: Session, assessment_id: int) -> dict:
    return get_assessment_storage().get(assessment_id)


def delete_assessment(db: Session, assessment_id: int) -> bool:
    return get_assessment_storage().delete(assessment_id)


def _sort_records(records: list[dict], sort_key: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir != "asc"

    def sort_value(record: dict):
        value = record.get(sort_key)
        if sort_key == "date_of_interview":
            return _safe_parse_date(value) or datetime.min.date()
        if sort_key == "created_at":
            return _safe_parse_datetime(value) or datetime.min.replace(tzinfo=timezone.utc)
        return str(value or "").lower()

    return sorted(records, key=sort_value, reverse=reverse)


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


def _safe_parse_datetime(value: str):
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
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
