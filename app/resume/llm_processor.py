import json
import logging
import os
from typing import Optional, Literal
from app.resume.schemas import StructuredResume
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMProcessor:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or settings.llm_provider
        if self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = model or "gpt-4-turbo-preview"
            self.deployment_id = None
        elif self.provider == "azure-openai":
            from openai import AzureOpenAI
            self.client = AzureOpenAI(
                api_key=settings.azure_openai_key,
                api_version="2024-02-15-preview",
                azure_endpoint=settings.azure_openai_endpoint
            )
            self.model = model or settings.azure_openai_deployment
            self.deployment_id = settings.azure_openai_deployment
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic(api_key=settings.anthropic_api_key)
            self.model = model or "claude-3-opus-20240229"
            self.deployment_id = None
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def process_resume(self, extracted_text: str) -> StructuredResume:
        schema_dict = StructuredResume.model_json_schema()
        prompt = self._build_resume_prompt(extracted_text, schema_dict)
        if self.provider in ("openai", "azure-openai"):
            response = self._call_openai(prompt)
        else:
            response = self._call_anthropic(prompt)
        resume_data = self._parse_json_response(response)
        resume_data = self._clean_resume_data(resume_data)
        return StructuredResume(**resume_data)

    def extract_skills_from_jd(self, jd_text: str) -> list[str]:
        prompt = f"""Extract and group the primary technical and professional skills from this job description.
Return a JSON array of skill group strings. Each string should be a meaningful skill category or specific skill.
Merge similar/related skills into one group. Return 6-12 skill groups maximum.

Job Description:
{jd_text}

Return only a JSON array like: ["Python & FastAPI", "SQL & Databases", "Cloud (AWS/Azure)", ...]"""
        if self.provider in ("openai", "azure-openai"):
            response = self._call_openai(prompt)
        else:
            response = self._call_anthropic(prompt)
        try:
            text = response.strip().strip("```json").strip("```").strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        return v
            return []
        except Exception:
            return []

    def generate_assessment_summary(self, candidate_name: str, assessment_status: str, skill_ratings: dict) -> str:
        ratings_lines = "\n".join(f"  - {skill}: {rating}" for skill, rating in skill_ratings.items())
        prompt = f"""Summarize this candidate assessment in 2 short sentences max.

Candidate: {candidate_name}
Status: {assessment_status}
Skill Ratings:
{ratings_lines}

Rules:
- Sentence 1: mention top strengths (Very Good/Good skills).
- Sentence 2: note any weak areas (Average/Low) and give a one-line recommendation matching the status.
- Plain text only, no JSON, no bullet points, no headings."""
        if self.provider in ("openai", "azure-openai"):
            response = self._call_openai(prompt)
        else:
            response = self._call_anthropic(prompt)

        # LLM sometimes wraps the text in JSON — extract the string value if so
        text = response.strip().strip("```json").strip("```").strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                # Take the first string value found regardless of key name
                for v in parsed.values():
                    if isinstance(v, str):
                        return v
        except Exception:
            pass
        return text

    def _build_resume_prompt(self, extracted_text: str, schema: dict) -> str:
        return f"""Extract and structure the following resume text into JSON format following this schema:

Schema:
{json.dumps(schema, indent=2)}

Resume Text:
{extracted_text}

Instructions:
1. Parse all resume information from the provided text
2. Organize data according to the schema
3. Return ONLY valid JSON that matches the schema
4. Use empty arrays for missing sections
5. NEVER return null/None for ANY field - provide default values if information is missing
6. For missing email: use ""
7. For missing dates: use "2024"
8. For missing text fields: use ""
9. For skills: group into meaningful categories. Each group must have a "category" string and a "skills" array.
10. For "designation": extract the candidate's current or most recent job title.
11. For "career_summary": extract the professional summary as a list of bullet-point strings.
12. For each experience entry, extract "client_name" (client org, may differ from employer). If not mentioned, use company name.
13. For each experience entry, extract "description" as a list of responsibility strings.

Return only the JSON object, no other text."""

    def _parse_json_response(self, response: str) -> dict:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        repaired = text.rstrip()
        if repaired and repaired[-1] in (",", ":"):
            repaired = repaired[:-1]
        if repaired.count('"') % 2 != 0:
            repaired += '"'
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        repaired += "]" * open_brackets + "}" * open_braces
        return json.loads(repaired)

    def _clean_resume_data(self, data: dict) -> dict:
        if "contact" not in data:
            data["contact"] = {}
        contact = data["contact"]
        full_name = contact.get("name") or ""
        contact["name"] = full_name
        name_parts = full_name.split() if full_name else []
        if not contact.get("first_name"):
            contact["first_name"] = name_parts[0] if name_parts else ""
        if not contact.get("last_name"):
            contact["last_name"] = " ".join(name_parts[1:]) if len(name_parts) >= 2 else ""
        contact["email"] = contact.get("email") or ""
        contact["phone"] = contact.get("phone") or ""
        contact["location"] = contact.get("location") or ""
        contact["linkedin"] = contact.get("linkedin") or ""
        contact["github"] = contact.get("github") or ""
        contact["notice_period"] = contact.get("notice_period") or ""
        contact["candidate_type"] = contact.get("candidate_type") or "External"
        contact["interview_availability"] = contact.get("interview_availability") or ""
        contact["start_availability"] = contact.get("start_availability") or ""
        contact["total_experience_years"] = contact.get("total_experience_years") or "0"
        contact["relevant_experience_years"] = contact.get("relevant_experience_years") or "0"
        contact["hacker_rank_score"] = contact.get("hacker_rank_score") or ""
        contact["worked_with_ford_before"] = contact.get("worked_with_ford_before") or "No"
        contact["worked_with_ford_agency_before"] = contact.get("worked_with_ford_agency_before") or "No"
        data["designation"] = data.get("designation") or ""
        data["summary"] = data.get("summary") or ""
        career_summary = data.get("career_summary")
        if not career_summary:
            summary_text = data.get("summary") or ""
            career_summary = [s.strip() for s in summary_text.replace("\n", ".").split(".") if s.strip()] if summary_text else []
        data["career_summary"] = career_summary
        if not data.get("experience"):
            data["experience"] = []
        for exp in data["experience"]:
            exp["company"] = exp.get("company") or ""
            exp["position"] = exp.get("position") or ""
            exp["client_name"] = exp.get("client_name") or exp.get("company") or ""
            exp["start_date"] = exp.get("start_date") or "2020"
            exp["end_date"] = exp.get("end_date") or "2024"
            exp["description"] = exp.get("description") or []
            exp["technologies"] = exp.get("technologies") or []
        if not data.get("education"):
            data["education"] = []
        for edu in data["education"]:
            edu["institution"] = edu.get("institution") or ""
            edu["degree"] = edu.get("degree") or ""
            edu["field_of_study"] = edu.get("field_of_study") or ""
            edu["graduation_date"] = edu.get("graduation_date") or "2024"
            edu["gpa"] = edu.get("gpa") or ""
        if not data.get("skills"):
            data["skills"] = []
        cleaned_skills = []
        for skill in data["skills"]:
            category = skill.get("category") or skill.get("name") or ""
            skills_list = skill.get("skills") or []
            if isinstance(skills_list, str):
                skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
            if category and skills_list:
                cleaned_skills.append({"category": category, "skills": skills_list})
        data["skills"] = cleaned_skills
        if not data.get("certifications"):
            data["certifications"] = []
        for cert in data["certifications"]:
            cert["name"] = cert.get("name") or ""
            cert["issuer"] = cert.get("issuer") or ""
            cert["date"] = cert.get("date") or "2024"
        if not isinstance(data.get("additional_info"), dict):
            data["additional_info"] = None
        return data

    def _call_openai(self, prompt: str) -> str:
        kwargs = dict(
            messages=[
                {"role": "system", "content": "You are a resume parsing expert. Return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=16000
        )
        if self.provider == "azure-openai":
            kwargs["model"] = self.deployment_id
        else:
            kwargs["model"] = self.model
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _call_anthropic(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system="You are a resume parsing expert. Return valid JSON.",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
