from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.auth.router import get_current_user
from app.database import get_db
from app.assessment import service as assessment_service
from app.reports.service import record_to_pdf, records_to_csv
from datetime import datetime

router = APIRouter()


@router.get("/{assessment_id}/export/pdf")
def export_assessment_pdf(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    record = assessment_service.get_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    try:
        pdf_bytes = record_to_pdf(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    safe_name = record["candidate_name"].replace(" ", "_")
    filename = f"assessment_{safe_name}_{_safe_date_part(record.get('date_of_interview'))}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/export/csv")
def export_all_csv(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    records = assessment_service.get_all_assessments(db)
    csv_content = records_to_csv(records)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=candidate_assessments_{timestamp}.csv"})


@router.get("/{assessment_id}/export/csv")
def export_single_csv(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    record = assessment_service.get_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    csv_content = records_to_csv([record])
    safe_name = record["candidate_name"].replace(" ", "_")
    filename = f"assessment_{safe_name}_{_safe_date_part(record.get('date_of_interview'))}.csv"
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def _safe_date_part(value) -> str:
    if not value:
        return datetime.now().strftime("%d-%m-%Y")
    raw = str(value).strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    raw = raw.replace("/", "-")
    parts = raw.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return raw
