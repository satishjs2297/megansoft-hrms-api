import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.auth.router import CurrentUser, require_permissions
from app.database import get_db
from app.assessment import service as assessment_service
from app.reports.service import record_to_pdf, records_to_csv
from app.security.rate_limiter import rate_limit

router = APIRouter()
audit_logger = logging.getLogger("audit")


@router.get("/{assessment_id}/export/pdf")
def export_assessment_pdf(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("app:full_access")),
    _: None = Depends(rate_limit("heavy")),
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
    _audit(
        action="reports.export_pdf",
        username=current_user.username,
        request=request,
        details={"assessment_id": assessment_id, "filename": filename},
    )
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/export/csv")
def export_all_csv(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("app:full_access")),
    _: None = Depends(rate_limit("heavy")),
):
    records = assessment_service.get_all_assessments(db)
    csv_content = records_to_csv(records, include_skill_columns=False)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"candidate_assessments_{timestamp}.csv"
    _audit(
        action="reports.export_all_csv",
        username=current_user.username,
        request=request,
        details={"records": len(records), "filename": filename},
    )
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/{assessment_id}/export/csv")
def export_single_csv(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permissions("app:full_access")),
    _: None = Depends(rate_limit("heavy")),
):
    record = assessment_service.get_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assessment not found")
    csv_content = records_to_csv([record])
    safe_name = record["candidate_name"].replace(" ", "_")
    filename = f"assessment_{safe_name}_{_safe_date_part(record.get('date_of_interview'))}.csv"
    _audit(
        action="reports.export_single_csv",
        username=current_user.username,
        request=request,
        details={"assessment_id": assessment_id, "filename": filename},
    )
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
