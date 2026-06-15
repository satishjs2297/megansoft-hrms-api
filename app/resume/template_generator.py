import os
import tempfile
import logging
import base64
from datetime import datetime
from io import BytesIO
from typing import Optional
from PIL import Image
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from app.resume.schemas import StructuredResume
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_resume_docx(resume_data: StructuredResume, template_path: str) -> bytes:
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    doc = DocxTemplate(template_path)
    photo_tmp_path: Optional[str] = None
    try:
        photo_tmp_path = _prepare_candidate_photo_file(resume_data)
        context = _prepare_context(resume_data, doc, photo_tmp_path)
        doc.render(context)
    finally:
        if photo_tmp_path and os.path.exists(photo_tmp_path):
            os.unlink(photo_tmp_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        doc.save(tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _prepare_context(resume_data: StructuredResume, doc: DocxTemplate, photo_tmp_path: Optional[str] = None) -> dict:
    contact = resume_data.contact
    certifications = _dedupe_certifications(resume_data.certifications)
    first_name = contact.first_name or ""
    last_name = contact.last_name or ""
    if not first_name and not last_name and contact.name:
        parts = contact.name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    relevant_skill_names = _resolve_relevant_skill_names(resume_data)
    relevant_skill_groups = _resolve_relevant_skill_groups(resume_data, relevant_skill_names)
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
        "notice_period": _format_notice_period(contact.notice_period),
        "candidate_type": contact.candidate_type or "External",
        "interview_availability": _format_ddmmyyyy_slash(contact.interview_availability),
        "start_availability": _format_ddmmyyyy_slash(contact.start_availability),
        "total_experience_years": contact.total_experience_years or "0",
        "relevant_experience_years": contact.relevant_experience_years or "0",
        "hacker_rank_score": contact.hacker_rank_score or "",
        "worked_with_ford_before": contact.worked_with_ford_before or "No",
        "worked_with_ford_agency_before": contact.worked_with_ford_agency_before or "No",
        "designation": resume_data.designation or "",
        "summary": resume_data.summary or "",
        "candidate_photo": InlineImage(doc, photo_tmp_path, width=Mm(35), height=Mm(45)) if photo_tmp_path else "",
        "career_summary": resume_data.career_summary or [],
        "relevant_skills": relevant_skill_groups,
        "relavent_skills": relevant_skill_groups,
        "relevantSkills": relevant_skill_groups,
        "relaventSkills": relevant_skill_groups,
        "relevant_skill_names": relevant_skill_names,
        "experience": [
            {
                "company": exp.company,
                "position": exp.position,
                "client_name": exp.client_name or exp.company,
                "start_date": _format_ddmmyyyy(exp.start_date),
                "end_date": _format_ddmmyyyy(exp.end_date) or "Present",
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
                "graduation_date": _format_ddmmyyyy(edu.graduation_date),
                "gpa": edu.gpa or "",
            }
            for edu in resume_data.education
        ],
        "skills": [{"category": s.category, "skills": s.skills} for s in resume_data.skills],
        "certifications": [
            {
                "name": c.name,
                "issuer": "",
                "date": "",
                "credential_id": "",
                "credential_url": "",
            }
            for c in certifications
        ],
        "certifications_secondary": [],
    }
    logger.info("relevant_skills in template context: %s", context["relevant_skills"])
    return context


def _prepare_candidate_photo_file(resume_data: StructuredResume) -> Optional[str]:
    raw = (resume_data.candidate_photo_base64 or "").strip()
    if not raw:
        raw = ((resume_data.additional_info or {}).get("candidate_photo_base64") or "").strip()
    if not raw:
        return None
    try:
        image_bytes = _decode_base64_image(raw)
        resized = _resize_to_indian_passport(image_bytes)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(resized)
            tmp.flush()
            logger.info("candidate photo prepared at path=%s", tmp.name)
            return tmp.name
    except Exception:
        logger.exception("candidate photo processing failed")
        return None


def _decode_base64_image(raw: str) -> bytes:
    payload = raw
    if "," in raw and raw.lower().startswith("data:"):
        payload = raw.split(",", 1)[1]
    return base64.b64decode(payload)


def _resize_to_indian_passport(image_bytes: bytes) -> bytes:
    target_w, target_h = 413, 531  # ~35x45mm at 300 DPI
    target_ratio = target_w / target_h
    with Image.open(BytesIO(image_bytes)) as img:
        converted = img.convert("RGB")
        src_w, src_h = converted.size
        src_ratio = src_w / src_h if src_h else target_ratio
        if src_ratio > target_ratio:
            crop_w = int(src_h * target_ratio)
            left = max(0, (src_w - crop_w) // 2)
            box = (left, 0, left + crop_w, src_h)
        else:
            crop_h = int(src_w / target_ratio) if target_ratio else src_h
            top = max(0, (src_h - crop_h) // 2)
            box = (0, top, src_w, top + crop_h)
        cropped = converted.crop(box)
        resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        out = BytesIO()
        resized.save(out, format="PNG")
        return out.getvalue()


def _resolve_relevant_skill_names(resume_data: StructuredResume) -> list[str]:
    if resume_data.relevant_skills:
        return resume_data.relevant_skills[:3]
    all_skills: list[str] = []
    for group in resume_data.skills:
        all_skills.extend(group.skills)
    seen: set[str] = set()
    unique: list[str] = []
    for skill in all_skills:
        key = skill.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(skill.strip())
    return unique[:3]


def _resolve_relevant_skill_groups(resume_data: StructuredResume, relevant_skill_names: list[str]) -> list[dict]:
    if not relevant_skill_names:
        return []
    resolved: list[dict] = []
    for name in _dedupe_keep_order(relevant_skill_names):
        skill_l = name.lower()
        category = "Relevant Skills"
        for group in resume_data.skills:
            if any(
                skill_l == (s or "").strip().lower()
                or skill_l in (s or "").strip().lower()
                or (s or "").strip().lower() in skill_l
                for s in group.skills
            ):
                category = group.category
                break
        # Keep one row per top skill so templates can render exactly top-3.
        resolved.append({"category": category, "skills": [name]})
    return resolved[:3]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def _dedupe_certifications(certifications) -> list:
    result = []
    seen: set[str] = set()
    for cert in certifications or []:
        name = _normalize_certification_part(getattr(cert, "name", ""))
        issuer = _normalize_certification_part(getattr(cert, "issuer", ""))
        date = _normalize_certification_part(getattr(cert, "date", ""))
        key = f"{name}|{issuer}|{date}".strip("|")
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(cert)
    return result


def _normalize_certification_part(value: str) -> str:
    text = str(value or "").strip().rstrip(".")
    text = " ".join(text.split())
    return text.lower()


def _format_notice_period(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return f"{text} Days"
    return text


def _format_ddmmyyyy(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    raw = str(value).strip()
    if not raw:
        return ""

    if "T" in raw:
        raw = raw.split("T", 1)[0]

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return str(value)


def _format_ddmmyyyy_slash(value) -> str:
    formatted = _format_ddmmyyyy(value)
    return formatted.replace("-", "/") if formatted else ""


def list_templates() -> list[dict]:
    templates_dir = settings.resolved_templates_dir
    if not os.path.exists(templates_dir):
        return []
    result = []
    for fname in os.listdir(templates_dir):
        if fname.lower().endswith(".docx"):
            result.append({"id": fname, "name": fname.replace("-", " ").replace("_", " ").replace(".docx", "").title(), "filename": fname})
    result.sort(key=lambda item: item["name"])
    return result
