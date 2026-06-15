import re
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

class Contact(BaseModel):
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    notice_period: Optional[str] = None
    candidate_type: Optional[str] = "External"
    interview_availability: Optional[str] = None
    start_availability: Optional[str] = None
    total_experience_years: Optional[str] = None
    relevant_experience_years: Optional[str] = None
    hacker_rank_score: Optional[str] = None
    worked_with_ford_before: Optional[str] = "No"
    worked_with_ford_agency_before: Optional[str] = "No"

class Experience(BaseModel):
    company: str
    position: str
    client_name: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    is_current: bool = False
    description: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)

class Education(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    graduation_date: str
    gpa: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)

class Skill(BaseModel):
    category: str
    skills: List[str]

class Project(BaseModel):
    title: str
    description: str
    technologies: List[str]
    link: Optional[str] = None
    date: Optional[str] = None

class Certification(BaseModel):
    name: str
    issuer: str
    date: str
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None

class Language(BaseModel):
    language: str
    proficiency: str

class StructuredResume(BaseModel):
    contact: Contact
    designation: Optional[str] = None
    summary: Optional[str] = None
    career_summary: List[str] = Field(default_factory=list)
    relevant_skills: List[str] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: List[Skill] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    languages: List[Language] = Field(default_factory=list)
    candidate_photo_base64: Optional[str] = None
    additional_info: Optional[dict] = None

    @model_validator(mode="after")
    def dedupe_certifications(self):
        merged: list[Certification] = []
        key_to_index: dict[str, int] = {}

        for cert in self.certifications or []:
            name = _clean_certification_name(cert.name)
            if not name:
                continue

            key = _canonical_certification_name_key(name)
            if not key:
                continue

            existing_index = key_to_index.get(key)
            if existing_index is None:
                credential_id = (cert.credential_id or "").strip() or _extract_credential_id_from_name(cert.name)
                merged.append(Certification(
                    name=name,
                    issuer=(cert.issuer or "").strip(),
                    date=(cert.date or "").strip(),
                    credential_id=credential_id,
                    credential_url=(cert.credential_url or "").strip(),
                ))
                key_to_index[key] = len(merged) - 1
                continue

            existing = merged[existing_index]
            existing.name = _prefer_certification_name(existing.name, name)
            existing.issuer = existing.issuer or (cert.issuer or "").strip()
            existing.date = _prefer_certification_date(existing.date, (cert.date or "").strip())
            existing.credential_id = existing.credential_id or (cert.credential_id or "").strip() or _extract_credential_id_from_name(cert.name)
            existing.credential_url = existing.credential_url or (cert.credential_url or "").strip()

        self.certifications = merged
        return self


def _clean_certification_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"\((?:[^)]*(?:certification|credential|license|licen[cs]e|id|number|no\.?)\s*[:#-]?[^)]*)\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\(([A-Z]{1,10}\d[\w.-]{3,})\)", "", text)
    text = re.sub(
        r"\s*(?:[-|,])?\s*(?:certification|credential|license|licen[cs]e)\s*(?:id|number|no\.?)\s*[:#-]\s*[A-Za-z0-9-]+\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\.\s*$", "", text)
    text = re.sub(r"^\s*certified\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    return text


def _extract_credential_id_from_name(name: str) -> str:
    text = str(name or "")
    if not text:
        return ""
    patterns = [
        r"(?:certification|credential|license|licen[cs]e|id|number|no\.?)\s*[:#-]\s*([A-Za-z0-9-]+)",
        r"\([A-Z]{2,10}\s+ID:\s*([A-Za-z0-9-]+)\)",
        r"\(([A-Z]{1,10}\d[\w.-]{3,})\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _normalize_certification_key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _canonical_certification_name_key(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\([A-Z0-9.+-]{2,12}\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    return _normalize_certification_key_part(text)


def _prefer_certification_name(current: str, candidate: str) -> str:
    current = str(current or "").strip()
    candidate = str(candidate or "").strip()
    if not current:
        return candidate
    if not candidate:
        return current

    current_clean = _clean_certification_name(current)
    candidate_clean = _clean_certification_name(candidate)

    current_noisy = current_clean.lower() != current.lower().strip()
    candidate_noisy = candidate_clean.lower() != candidate.lower().strip()
    if current_noisy != candidate_noisy:
        return candidate if candidate_noisy is False else current

    current_key = re.sub(r"[^a-z0-9]+", "", current_clean.lower())
    candidate_key = re.sub(r"[^a-z0-9]+", "", candidate_clean.lower())
    if current_key and current_key == candidate_key:
        current_tokens = len(re.findall(r"[A-Za-z0-9]+", current_clean))
        candidate_tokens = len(re.findall(r"[A-Za-z0-9]+", candidate_clean))
        if candidate_tokens != current_tokens:
            return candidate_clean if candidate_tokens > current_tokens else current_clean

    if len(candidate_clean) < len(current_clean):
        return candidate_clean or candidate
    return current_clean or current


def _prefer_certification_date(current: str, candidate: str) -> str:
    current = str(current or "").strip()
    candidate = str(candidate or "").strip()
    if not current:
        return candidate
    if not candidate:
        return current
    return candidate if len(candidate) > len(current) else current
