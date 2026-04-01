import os
import tempfile
import logging
from docxtpl import DocxTemplate
from app.resume.schemas import StructuredResume
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_resume_docx(resume_data: StructuredResume, template_path: str) -> bytes:
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    doc = DocxTemplate(template_path)
    context = _prepare_context(resume_data)
    doc.render(context)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        doc.save(tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _prepare_context(resume_data: StructuredResume) -> dict:
    contact = resume_data.contact
    first_name = contact.first_name or ""
    last_name = contact.last_name or ""
    if not first_name and not last_name and contact.name:
        parts = contact.name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    context = {
        "name": contact.name,
        "first_name": first_name,
        "last_name": last_name,
        "u_first_name": first_name,
        "u_last_name": last_name,
        "email": contact.email or "",
        "phone": contact.phone or "",
        "location": contact.location or "",
        "linkedin": contact.linkedin or "",
        "github": contact.github or "",
        "website": contact.website or "",
        "notice_period": contact.notice_period or "",
        "candidate_type": contact.candidate_type or "External",
        "interview_availability": contact.interview_availability or "",
        "start_availability": contact.start_availability or "",
        "total_experience_years": contact.total_experience_years or "0",
        "relevant_experience_years": contact.relevant_experience_years or "0",
        "hacker_rank_score": contact.hacker_rank_score or "",
        "worked_with_ford_before": contact.worked_with_ford_before or "No",
        "worked_with_ford_agency_before": contact.worked_with_ford_agency_before or "No",
        "designation": resume_data.designation or "",
        "summary": resume_data.summary or "",
        "career_summary": resume_data.career_summary or [],
        "experience": [
            {
                "company": exp.company,
                "position": exp.position,
                "client_name": exp.client_name or exp.company,
                "start_date": exp.start_date,
                "end_date": exp.end_date or "Present",
                "description": exp.description,
                "responsibilites": exp.description,
                "technologies": exp.technologies or [],
            }
            for exp in resume_data.experience
        ],
        "education": [
            {
                "institution": edu.institution,
                "degree": edu.degree,
                "field_of_study": edu.field_of_study,
                "graduation_date": edu.graduation_date,
                "gpa": edu.gpa or "",
            }
            for edu in resume_data.education
        ],
        "skills": [{"category": s.category, "skills": s.skills} for s in resume_data.skills],
        "certifications": [
            {"name": c.name, "issuer": c.issuer, "date": c.date}
            for c in resume_data.certifications
        ],
    }
    return context


def list_templates() -> list[dict]:
    templates_dir = settings.templates_dir
    if not os.path.exists(templates_dir):
        return []
    result = []
    for fname in os.listdir(templates_dir):
        if fname.endswith(".docx"):
            result.append({"id": fname, "name": fname.replace("-", " ").replace("_", " ").replace(".docx", "").title(), "filename": fname})
    return result
