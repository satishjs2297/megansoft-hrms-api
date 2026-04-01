from pydantic import BaseModel
from typing import Optional, Dict, Literal
from datetime import datetime

AssessmentStatus = Literal["Select", "Above Average", "Reject", "Strong Reject", "On Hold"]
SkillRating = Literal["Very Good", "Good", "Average", "Low"]

class AssessmentCreate(BaseModel):
    candidate_name: str
    panel_name: str
    date_of_interview: str
    assessment_status: AssessmentStatus
    skills_assessment: Dict[str, SkillRating]
    overall_observation: Optional[str] = ""
    job_description_text: Optional[str] = ""

class AssessmentResponse(BaseModel):
    id: int
    candidate_name: str
    panel_name: str
    date_of_interview: str
    assessment_status: str
    skills_assessment: Dict[str, str]
    overall_observation: Optional[str]
    job_description_text: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

class AssessmentListItem(BaseModel):
    id: int
    candidate_name: str
    panel_name: str
    date_of_interview: str
    assessment_status: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
