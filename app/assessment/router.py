import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict
from pydantic import BaseModel
from app.auth.router import CurrentUser, require_permissions
from app.database import get_db
from app.assessment.schemas import AssessmentCreate
from app.assessment import service
from app.resume.llm_processor import LLMProcessor
from app.security.rate_limiter import rate_limit


class SummarizeRequest(BaseModel):
    candidate_name: str
    assessment_status: str
    skill_ratings: Dict[str, str]

router = APIRouter()
audit_logger = logging.getLogger("audit")


@router.post("/summarize")
def summarize_assessment(
    data: SummarizeRequest,
    current_user: CurrentUser = Depends(require_permissions("assessment:write")),
    _: None = Depends(rate_limit("heavy")),
):
    try:
        processor = LLMProcessor()
        summary = processor.generate_assessment_summary(
            candidate_name=data.candidate_name,
            assessment_status=data.assessment_status,
            skill_ratings=data.skill_ratings,
        )
        return {"summary": summary.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


@router.post("")
def create_assessment(
    request: Request,
    data: AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        request_hash = service.compute_request_hash(data)
        existing = service.get_idempotent_response(db, idempotency_key)
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key reused with different payload")
            return json.loads(existing.response_json)

        created = service.create_assessment(db, data)
        service.save_idempotent_response(db, idempotency_key, request_hash, created, status_code=200)
        _audit(
            action="assessment.create",
            username=current_user.username,
            request=request,
            details={"assessment_id": created.get("id"), "idempotency_key": idempotency_key},
        )
        return created

    created = service.create_assessment(db, data)
    _audit(
        action="assessment.create",
        username=current_user.username,
        request=request,
        details={"assessment_id": created.get("id"), "idempotency_key": None},
    )
    return created


@router.get("")
def list_assessments(
    search: str = "",
    panelName: str = "",
    feedbackStatus: str = "",
    fromDate: str = "",
    toDate: str = "",
    sortBy: str = "created_at",
    sortOrder: str = "desc",
    pageNo: int = 1,
    maxRecords: int = 10,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
):
    pageNo = max(pageNo, 1)
    maxRecords = max(maxRecords, 1)

    records = service.get_all_assessments(
        db,
        search=search,
        panel_name=panelName,
        feedback_status=feedbackStatus,
        date_from=fromDate,
        date_to=toDate,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    total = len(records)
    selected = sum(1 for r in records if "Select" in r["assessment_status"])
    rejected = sum(1 for r in records if "Reject" in r["assessment_status"])
    on_hold = sum(1 for r in records if r["assessment_status"] == "On Hold")
    status_counts: Dict[str, int] = {}
    for r in records:
        key = r["assessment_status"]
        status_counts[key] = status_counts.get(key, 0) + 1

    total_pages = (total + maxRecords - 1) // maxRecords if total > 0 else 1
    start = (pageNo - 1) * maxRecords
    end = start + maxRecords
    paged_records = records[start:end]

    return {
        "records": paged_records,
        "summary": {"total": total, "selected": selected, "rejected": rejected, "on_hold": on_hold},
        "status_counts": status_counts,
        "pagination": {
            "pageNo": pageNo,
            "maxRecords": maxRecords,
            "totalRecords": total,
            "totalPages": total_pages,
        }
    }


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
):
    record = service.get_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return record


@router.delete("/{assessment_id}")
def delete_assessment(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
):
    deleted = service.delete_assessment(db, assessment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assessment not found")
    _audit(
        action="assessment.delete",
        username=current_user.username,
        request=request,
        details={"assessment_id": assessment_id},
    )
    return {"message": "Deleted successfully"}


def _audit(action: str, username: str, request: Request, details: dict | None = None):
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "username": username,
        "request_id": getattr(request.state, "request_id", None),
        "ip": request.client.host if request.client else None,
        "details": details or {},
    }
    audit_logger.info(json.dumps(payload))
