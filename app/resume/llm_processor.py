import json
import logging
import os
import time
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
            self.model = model or settings.llm_model or "gpt-4-turbo-preview"
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
        started = time.perf_counter()
        prompt = self._build_resume_prompt(extracted_text)
        try:
            if self.provider in ("openai", "azure-openai"):
                response = self._call_openai(prompt)
            else:
                response = self._call_anthropic(prompt)
            try:
                resume_data = self._parse_json_response(response)
            except Exception:
                # Resume JSON can be truncated at low token caps; retry once with a larger cap.
                retry_tokens = max(7000, settings.llm_max_completion_tokens * 2)
                logger.warning(
                    "process_resume parse failed; retrying once with higher token cap provider=%s model=%s retry_tokens=%s",
                    self.provider,
                    self.model,
                    retry_tokens,
                )
                if self.provider in ("openai", "azure-openai"):
                    response = self._call_openai(prompt, max_completion_tokens_override=retry_tokens)
                else:
                    response = self._call_anthropic(prompt)
                resume_data = self._parse_json_response(response)
            resume_data = self._clean_resume_data(resume_data)
            return StructuredResume(**resume_data)
        except Exception:
            logger.exception("process_resume failed provider=%s model=%s", self.provider, self.model)
            raise
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= settings.llm_slow_log_threshold_seconds:
                logger.warning("process_resume slow provider=%s model=%s elapsed=%.2fs", self.provider, self.model, elapsed)

    def extract_skills_from_jd(self, jd_text: str) -> list[str]:
        started = time.perf_counter()
        prompt = f"""Extract and group the primary technical and professional skills from this job description.
Return a JSON array of skill group strings. Each string should be a meaningful skill category or specific skill.
Merge similar/related skills into one group. Return 6-12 skill groups maximum.

Job Description:
{jd_text}

Return only a JSON array like: ["Python & FastAPI", "SQL & Databases", "Cloud (AWS/Azure)", ...]"""
        try:
            if self.provider in ("openai", "azure-openai"):
                response = self._call_openai(prompt)
            else:
                response = self._call_anthropic(prompt)
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
            logger.exception("extract_skills_from_jd failed provider=%s model=%s", self.provider, self.model)
            return []
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= settings.llm_slow_log_threshold_seconds:
                logger.warning("extract_skills_from_jd slow provider=%s model=%s elapsed=%.2fs", self.provider, self.model, elapsed)

    def generate_assessment_summary(self, candidate_name: str, assessment_status: str, skill_ratings: dict) -> str:
        started = time.perf_counter()
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
        try:
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
        except Exception:
            logger.exception("generate_assessment_summary failed provider=%s model=%s", self.provider, self.model)
            raise
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= settings.llm_slow_log_threshold_seconds:
                logger.warning("generate_assessment_summary slow provider=%s model=%s elapsed=%.2fs", self.provider, self.model, elapsed)

    def _build_resume_prompt(self, extracted_text: str) -> str:
        return f"""You are a professional resume writer. Parse and ENHANCE the resume below into structured JSON.

GOAL: Produce an improved, client-ready version that gets the candidate shortlisted.

ENHANCEMENT RULES:
- Preserve ALL responsibilities, technologies, skills, and achievements — do NOT drop or condense any content.
- Rewrite each responsibility bullet using strong action verbs (Led, Architected, Designed, Implemented, Optimized, Delivered, Migrated, Automated, etc.).
- Where possible, add impact/outcome phrasing (e.g., "reducing deployment time" or "improving performance" or "ensuring zero-downtime").
- Fix grammar, punctuation, and inconsistent formatting.
- Remove filler phrases ("Involved in", "Worked on", "Working on") — replace with direct action statements.
- Keep technical accuracy — do not invent technologies or achievements not implied by the original text.
- Maintain the professional tone suitable for client submission.

Return this exact JSON structure:
{{
  "contact": {{
    "name": "Full Name",
    "first_name": "First",
    "last_name": "Last",
    "email": "email or empty string",
    "phone": "phone or empty string",
    "location": "city/state or empty string",
    "linkedin": "URL or empty string",
    "github": "URL or empty string",
    "total_experience_years": "number as string or 0",
    "relevant_experience_years": "number as string or 0"
  }},
  "designation": "current or most recent job title",
  "summary": "2-3 sentence professional summary highlighting key strengths, years of experience, and core expertise",
  "career_summary": ["enhanced professional bullet points covering key competencies — preserve all points from original, rewrite for impact"],
  "experience": [
    {{
      "company": "employer name",
      "position": "job title",
      "client_name": "client org if mentioned, else same as company",
      "start_date": "MM/YYYY or YYYY",
      "end_date": "MM/YYYY or YYYY or Present",
      "is_current": true,
      "description": ["ALL responsibilities from original — each rewritten with action verbs and impact language"],
      "technologies": ["ALL technologies mentioned for this role"]
    }}
  ],
  "education": [
    {{
      "institution": "university",
      "degree": "degree name",
      "field_of_study": "field",
      "graduation_date": "YYYY",
      "gpa": "GPA or empty string"
    }}
  ],
  "skills": [
    {{"category": "group name", "skills": ["skill1", "skill2"]}}
  ],
  "certifications": [
    {{
      "name": "cert name",
      "issuer": "issuing org",
      "date": "YYYY or empty string",
      "credential_id": "ID or empty string"
    }}
  ],
  "projects": [],
  "languages": [],
  "additional_info": null
}}

OUTPUT RULES:
- Return ONLY valid JSON, no markdown, no explanation.
- Use empty string "" for missing text fields, empty arrays [] for missing lists.
- Never return null for string fields — use "".
- Do NOT merge or skip any experience roles — include every role from the original.
- Do NOT drop any responsibility bullets — enhance each one.
- Do NOT invent new skills or technologies not present in the original.
- skills: group into 6-12 meaningful categories.

Resume Text:
{extracted_text}"""

    def _parse_json_response(self, response: str) -> dict:
        text = response.strip()
        if not text:
            raise ValueError("LLM returned empty response")
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        if not text:
            raise ValueError("LLM returned empty response after markdown cleanup")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        first_obj = text.find("{")
        last_obj = text.rfind("}")
        if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
            candidate = text[first_obj:last_obj + 1]
            try:
                return json.loads(candidate)
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

    def _call_openai(self, prompt: str, max_completion_tokens_override: Optional[int] = None) -> str:
        max_completion_tokens = max(256, max_completion_tokens_override or settings.llm_max_completion_tokens)
        started = time.perf_counter()
        kwargs = dict(
            messages=[
                {"role": "system", "content": "You are a resume parsing expert. Return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )
        # OpenAI GPT-5 models require max_completion_tokens; Azure OpenAI chat uses max_tokens.
        if self.provider == "openai":
            kwargs["max_completion_tokens"] = max_completion_tokens
        else:
            kwargs["temperature"] = 0.3
            kwargs["max_tokens"] = max_completion_tokens
        if self.provider == "azure-openai":
            kwargs["model"] = self.deployment_id
        else:
            kwargs["model"] = self.model
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception:
            logger.exception(
                "_call_openai failed provider=%s model=%s max_completion_tokens=%s",
                self.provider,
                kwargs.get("model"),
                max_completion_tokens,
            )
            raise

        elapsed = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        if elapsed >= settings.llm_slow_log_threshold_seconds:
            logger.warning(
                "_call_openai slow provider=%s model=%s elapsed=%.2fs prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                self.provider,
                kwargs.get("model"),
                elapsed,
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
                getattr(usage, "total_tokens", None),
            )
        else:
            logger.info(
                "_call_openai ok provider=%s model=%s elapsed=%.2fs total_tokens=%s",
                self.provider,
                kwargs.get("model"),
                elapsed,
                getattr(usage, "total_tokens", None),
            )
        finish_reason = response.choices[0].finish_reason if response.choices else None
        content = response.choices[0].message.content if response.choices else None
        if finish_reason == "length":
            logger.warning(
                "_call_openai truncated provider=%s model=%s finish_reason=%s max_completion_tokens=%s",
                self.provider,
                kwargs.get("model"),
                finish_reason,
                max_completion_tokens,
            )
        if not content:
            logger.error(
                "_call_openai empty content provider=%s model=%s finish_reason=%s",
                self.provider,
                kwargs.get("model"),
                finish_reason,
            )
            raise ValueError("LLM returned empty content")
        return content

    def _call_anthropic(self, prompt: str) -> str:
        started = time.perf_counter()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max(256, settings.llm_max_completion_tokens),
                system="You are a resume parsing expert. Return valid JSON.",
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception:
            logger.exception("_call_anthropic failed provider=%s model=%s", self.provider, self.model)
            raise

        elapsed = time.perf_counter() - started
        if elapsed >= settings.llm_slow_log_threshold_seconds:
            logger.warning("_call_anthropic slow provider=%s model=%s elapsed=%.2fs", self.provider, self.model, elapsed)
        else:
            logger.info("_call_anthropic ok provider=%s model=%s elapsed=%.2fs", self.provider, self.model, elapsed)
        return response.content[0].text
