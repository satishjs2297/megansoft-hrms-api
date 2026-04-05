from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from pydantic import BaseModel
from app.auth.router import CurrentUser, require_permissions
from app.database import get_db
from app.assessment.schemas import AssessmentCreate
from app.assessment import service
from app.resume.llm_processor import LLMProcessor


class SummarizeRequest(BaseModel):
    candidate_name: str
    assessment_status: str
    skill_ratings: Dict[str, str]

router = APIRouter()


@router.post("/summarize")
def summarize_assessment(
    data: SummarizeRequest,
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
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
    data: AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
):
    return service.create_assessment(db, data)


@router.get("")
def list_assessments(
    search: str = "",
    panelName: str = "",
    feedbackStatus: str = "",
    fromDate: str = "",
    toDate: str = "",
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
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("assessment:write"))
):
    deleted = service.delete_assessment(db, assessment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {"message": "Deleted successfully"}
