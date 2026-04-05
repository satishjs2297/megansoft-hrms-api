import os
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import Response
from app.auth.router import CurrentUser, require_permissions
from app.resume.schemas import StructuredResume
from app.resume.extractor import extract_text
from app.resume.llm_processor import LLMProcessor
from app.resume.template_generator import generate_resume_docx, list_templates
from app.config import get_settings
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
settings = get_settings()


class ExtractResponse(BaseModel):
    extracted_text: str
    file_type: str


class SkillExtractionRequest(BaseModel):
    jd_text: str


class StructureResumeRequest(BaseModel):
    extracted_text: str
    job_description_text: Optional[str] = ""


@router.post("/extract", response_model=ExtractResponse)
async def extract_resume_text(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permissions("app:full_access"))
):
    content = await file.read()
    try:
        text, file_type = extract_text(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ExtractResponse(extracted_text=text, file_type=file_type)


@router.post("/structure", response_model=StructuredResume)
async def structure_resume(
    payload: StructureResumeRequest,
    current_user: CurrentUser = Depends(require_permissions("app:full_access"))
):
    extracted_text = payload.extracted_text
    if not extracted_text:
        raise HTTPException(status_code=400, detail="extracted_text is required")
    job_description_text = payload.job_description_text or ""
    processor = LLMProcessor()
    try:
        resume = processor.process_resume(extracted_text, job_description_text=job_description_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM processing failed: {str(e)}")
    return resume


@router.post("/generate")
async def generate_resume(
    resume_data: StructuredResume,
    template_id: str = "ford-india-resume-template.docx",
    current_user: CurrentUser = Depends(require_permissions("app:full_access"))
):
    template_path = os.path.join(settings.resolved_templates_dir, template_id)
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    try:
        docx_bytes = generate_resume_docx(resume_data, template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
    candidate_name = resume_data.contact.name.replace(" ", "_") or "resume"
    filename = f"{candidate_name}_resume.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permissions("app:full_access"))
):
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx templates allowed")
    content = await file.read()
    save_path = os.path.join(settings.resolved_templates_dir, file.filename)
    with open(save_path, "wb") as f:
        f.write(content)
    return {"message": "Template uploaded", "template_id": file.filename}


@router.get("/templates")
def get_templates(current_user: CurrentUser = Depends(require_permissions("app:full_access"))):
    return list_templates()


@router.post("/extract-jd-skills")
async def extract_jd_skills(
    payload: SkillExtractionRequest,
    current_user: CurrentUser = Depends(require_permissions("resume:extract_jd_skills"))
):
    processor = LLMProcessor()
    try:
        skills = processor.extract_skills_from_jd(payload.jd_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Skill extraction failed: {str(e)}")
    return {"skill_groups": skills}
