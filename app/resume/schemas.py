from typing import List, Optional
from pydantic import BaseModel, Field

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
