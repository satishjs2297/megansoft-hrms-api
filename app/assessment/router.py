from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from pydantic import BaseModel
from app.auth.router import get_current_user
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
    current_user: str = Depends(get_current_user)
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
    current_user: str = Depends(get_current_user)
):
    return service.create_assessment(db, data)


@router.get("")
def list_assessments(
    search: str = "",
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    records = service.get_all_assessments(db, search)
    total = len(records)
    selected = sum(1 for r in records if "Select" in r["assessment_status"])
    rejected = sum(1 for r in records if "Reject" in r["assessment_status"])
    on_hold = sum(1 for r in records if r["assessment_status"] == "On Hold")
    return {
        "records": records,
        "summary": {"total": total, "selected": selected, "rejected": rejected, "on_hold": on_hold}
    }


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    record = service.get_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return record


@router.delete("/{assessment_id}")
def delete_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    deleted = service.delete_assessment(db, assessment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {"message": "Deleted successfully"}
