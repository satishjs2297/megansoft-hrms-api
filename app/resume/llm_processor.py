import json
import logging
import re
import time
from typing import Optional
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

    def process_resume(self, extracted_text: str, job_description_text: str = "") -> StructuredResume:
        started = time.perf_counter()
        prompt = self._build_resume_prompt(extracted_text, job_description_text=job_description_text)
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
            resume_data = self._clean_resume_data(
                resume_data,
                job_description_text=job_description_text,
                extracted_text=extracted_text,
            )
            logger.info("relevant_skills selected: %s", resume_data.get("relevant_skills", []))
            structured_resume = StructuredResume(**resume_data)
            structured_resume.certifications = self._dedupe_certification_models(structured_resume.certifications)
            return structured_resume
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

    def _build_resume_prompt(self, extracted_text: str, job_description_text: str = "") -> str:
        jd_section = f"""

JOB DESCRIPTION (use this to tailor output and identify top 3 relevant skills):
{job_description_text}
""" if job_description_text else ""
        return f"""You are a professional resume writer. Parse and ENHANCE the resume below into structured JSON.

GOAL: Produce an improved, client-ready version that gets the candidate shortlisted.

ENHANCEMENT RULES:
- Preserve ALL responsibilities, technologies, skills, achievements, and certifications — do NOT drop or condense any content.
- Preserve and extract ALL certification names, issuers, completion dates, credential IDs, and credential URLs found anywhere in the resume.
- Rewrite each responsibility bullet using strong action verbs (Led, Architected, Designed, Implemented, Optimized, Delivered, Migrated, Automated, etc.).
- Where possible, add impact/outcome phrasing (e.g., "reducing deployment time" or "improving performance" or "ensuring zero-downtime").
- Fix grammar, punctuation, and inconsistent formatting.
- Remove filler phrases ("Involved in", "Worked on", "Working on") — replace with direct action statements.
- Keep technical accuracy — do not invent technologies or achievements not implied by the original text.
- Maintain the professional tone suitable for client submission.

JD ALIGNMENT RULES (apply when Job Description is provided):
- Re-rank and emphasize the candidate's existing experience to best match JD priorities.
- Rewrite each experience description bullet to foreground JD-relevant skills, tools, and business outcomes.
- Use JD terminology naturally in summary, career_summary, and experience bullets when supported by the resume.
- Prefer JD-relevant responsibilities first in each role, while still keeping all original responsibilities.
- Do NOT fabricate new projects, tools, domains, certifications, or measurable outcomes not grounded in the resume.

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
  "relevant_skills": ["top skill 1", "top skill 2", "top skill 3"],
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
      "credential_id": "ID or empty string",
      "credential_url": "URL or empty string"
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
- relevant_skills must always contain exactly 3 distinct skills taken from the candidate's actual resume skills/technologies.
- When a job description is provided, relevant_skills must be the 3 resume-backed skills that best match the job description priorities.
- certifications must include every certification mentioned in the resume, even when only partial details are available.
- If JD is provided, summary and experience descriptions must be explicitly optimized for JD fit using only truthful resume evidence.
- Do NOT merge or skip any experience roles — include every role from the original.
- Do NOT drop any responsibility bullets — enhance each one.
- Do NOT invent new skills or technologies not present in the original.
- skills: group into 6-12 meaningful categories.

Resume Text:
{extracted_text}
{jd_section}"""

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

    def _clean_resume_data(self, data: dict, job_description_text: str = "", extracted_text: str = "") -> dict:
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
        contact["notice_period"] = self._normalize_notice_period(contact.get("notice_period"))
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
        relevant_skills = data.get("relevant_skills") or []
        if isinstance(relevant_skills, str):
            relevant_skills = [s.strip() for s in relevant_skills.split(",") if s.strip()]
        relevant_skills = [str(s).strip() for s in relevant_skills if str(s).strip()]
        data["relevant_skills"] = self._select_relevant_skills(
            data,
            llm_relevant_skills=relevant_skills,
            job_description_text=job_description_text,
        )
        certifications = data.get("certifications")
        if not certifications:
            certifications = (
                data.get("certificate")
                or data.get("certification")
                or data.get("certs")
                or []
            )
        if isinstance(certifications, dict):
            certifications = [certifications]
        cleaned_certifications = []
        for cert in certifications:
            if isinstance(cert, str):
                name = cert.strip()
                if not name:
                    continue
                cleaned_certifications.append({
                    "name": name,
                    "issuer": "",
                    "date": "",
                    "credential_id": "",
                    "credential_url": "",
                })
                continue
            if not isinstance(cert, dict):
                continue
            name = (
                cert.get("name")
                or cert.get("title")
                or cert.get("certificate_name")
                or cert.get("certification_name")
                or ""
            )
            issuer = (
                cert.get("issuer")
                or cert.get("issuing_organization")
                or cert.get("issuing_org")
                or cert.get("organization")
                or cert.get("authority")
                or ""
            )
            date = (
                cert.get("date")
                or cert.get("issued_date")
                or cert.get("completion_date")
                or cert.get("year")
                or ""
            )
            credential_id = (
                cert.get("credential_id")
                or cert.get("credentialId")
                or cert.get("license_number")
                or cert.get("certificate_id")
                or ""
            )
            credential_url = (
                cert.get("credential_url")
                or cert.get("credentialUrl")
                or cert.get("url")
                or cert.get("link")
                or ""
            )
            if not any([name, issuer, date, credential_id, credential_url]):
                continue
            cleaned_certifications.append({
                "name": name,
                "issuer": issuer,
                "date": date,
                "credential_id": credential_id,
                "credential_url": credential_url,
            })
        extracted_certifications = self._extract_certifications_from_text(extracted_text)
        data["certifications"] = self._merge_certifications(cleaned_certifications, extracted_certifications)
        if not isinstance(data.get("additional_info"), dict):
            data["additional_info"] = None
        return data

    def _select_relevant_skills(
        self,
        data: dict,
        llm_relevant_skills: list[str],
        job_description_text: str = "",
    ) -> list[str]:
        candidates = self._collect_skill_candidates(data)
        if not candidates:
            return []

        if not (job_description_text or "").strip():
            ranked = sorted(
                candidates.values(),
                key=lambda row: (-row["resume_score"], row["first_seen"], row["name"].lower()),
            )
            return [row["name"] for row in ranked[:3]]

        jd_text = job_description_text or ""
        jd_lower = jd_text.lower()
        jd_tokens = set(self._tokenize_text(jd_text))
        llm_hint_keys = {self._normalize_skill_key(skill) for skill in llm_relevant_skills if skill.strip()}

        scored: list[tuple[float, int, str]] = []
        for row in candidates.values():
            skill = row["name"]
            key = row["key"]
            aliases = self._skill_aliases(skill)
            exact_phrase_hits = sum(self._count_alias_occurrences(jd_lower, alias) for alias in aliases)
            alias_token_hits = sum(1 for alias in aliases if alias in jd_tokens)

            skill_tokens = [token for token in self._tokenize_text(skill) if token not in self._skill_stopwords()]
            overlap_count = sum(1 for token in skill_tokens if token in jd_tokens)
            overlap_ratio = (overlap_count / len(skill_tokens)) if skill_tokens else 0.0
            partial_match_bonus = 0.0
            if skill_tokens and overlap_ratio >= 0.5:
                partial_match_bonus = 1.5

            llm_hint_bonus = 0.75 if key in llm_hint_keys else 0.0
            score = (
                (exact_phrase_hits * 5.0)
                + (alias_token_hits * 3.0)
                + (overlap_count * 2.0)
                + partial_match_bonus
                + row["resume_score"]
                + llm_hint_bonus
            )
            scored.append((score, row["first_seen"], skill))

        scored.sort(key=lambda row: (-row[0], row[1], row[2].lower()))
        matched = [skill for score, _, skill in scored if score > 0]
        top = self._dedupe_case_insensitive(matched)[:3]
        if len(top) < 3:
            fallback = [
                row["name"]
                for row in sorted(
                    candidates.values(),
                    key=lambda item: (-item["resume_score"], item["first_seen"], item["name"].lower()),
                )
            ]
            for skill in fallback:
                if skill.lower() not in {s.lower() for s in top}:
                    top.append(skill)
                if len(top) == 3:
                    break
        return top[:3]

    def _collect_skill_candidates(self, data: dict) -> dict[str, dict]:
        candidates: dict[str, dict] = {}
        first_seen = 0

        def add_candidate(skill_name: str, source_weight: float):
            nonlocal first_seen
            name = str(skill_name).strip()
            if not name:
                return
            key = self._normalize_skill_key(name)
            if not key:
                return
            if key not in candidates:
                candidates[key] = {
                    "name": name,
                    "key": key,
                    "resume_score": 0.0,
                    "first_seen": first_seen,
                }
                first_seen += 1
            elif len(name) < len(candidates[key]["name"]):
                candidates[key]["name"] = name
            candidates[key]["resume_score"] += source_weight

        for skill_group in data.get("skills", []):
            category = str(skill_group.get("category") or "").strip()
            if category and category.lower() not in {"skills", "technical skills", "relevant skills"}:
                add_candidate(category, 0.5)
            for skill in skill_group.get("skills") or []:
                for variant in self._expand_skill_variants(str(skill)):
                    add_candidate(variant, 2.0)

        for exp in data.get("experience", []):
            for tech in exp.get("technologies") or []:
                for variant in self._expand_skill_variants(str(tech)):
                    add_candidate(variant, 1.5)

        return candidates

    def _normalize_skill_key(self, value: str) -> str:
        cleaned_value = self._clean_skill_phrase(value)
        tokens = [token for token in self._tokenize_text(cleaned_value) if token not in self._skill_stopwords()]
        return " ".join(tokens)

    def _skill_aliases(self, skill: str) -> list[str]:
        aliases = {self._normalize_skill_key(skill)}
        raw = skill.strip().lower()
        if raw:
            aliases.add(raw)
        compact = re.sub(r"[^a-z0-9+#.]+", "", raw)
        if compact:
            aliases.add(compact)
        return [alias for alias in aliases if alias]

    def _expand_skill_variants(self, value: str) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []

        variants: list[str] = []

        def add_variant(candidate: str):
            candidate = candidate.strip()
            if not candidate:
                return
            if candidate.lower() not in {item.lower() for item in variants}:
                variants.append(candidate)

        add_variant(raw)
        cleaned = self._clean_skill_phrase(raw)
        add_variant(cleaned)

        for part in re.split(r"[/|,&]", raw):
            add_variant(self._clean_skill_phrase(part))

        return variants

    def _clean_skill_phrase(self, value: str) -> str:
        cleaned = str(value or "").strip()
        cleaned = re.sub(r"\(.*?\)", " ", cleaned)
        cleaned = re.sub(r"^[\-\u2022\s]+", "", cleaned)
        cleaned = re.sub(
            r"^(core|advanced|hands[\s-]?on|strong|extensive|basic|expert|proficient|experienced|experience|working|good)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(knowledge of|experience in|expertise in)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:;")
        return cleaned

    def _count_alias_occurrences(self, haystack: str, alias: str) -> int:
        escaped = re.escape(alias)
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
        return len(re.findall(pattern, haystack))

    def _tokenize_text(self, value: str) -> list[str]:
        return re.findall(r"[a-z0-9+#.]+", (value or "").lower())

    def _skill_stopwords(self) -> set[str]:
        return {
            "and",
            "or",
            "with",
            "in",
            "of",
            "to",
            "for",
            "the",
            "a",
            "an",
        }

    def _dedupe_case_insensitive(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(value.strip())
        return result

    def _normalize_notice_period(self, value) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if re.fullmatch(r"\d+", text):
            return f"{text} Days"
        return text

    def _extract_certifications_from_text(self, extracted_text: str) -> list[dict]:
        text = str(extracted_text or "").replace("\r\n", "\n")
        if not text.strip():
            return []

        lines = [line.strip(" \t•-*") for line in text.splitlines()]
        collected: list[dict] = []
        in_section = False

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if in_section:
                    break
                continue

            normalized = re.sub(r"[^a-z ]+", " ", line.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()

            if normalized in {
                "certifications",
                "certification",
                "professional certifications",
                "licenses certifications",
                "certificates",
            }:
                in_section = True
                continue

            if not in_section:
                continue

            if self._looks_like_resume_section_heading(line):
                break

            parsed = self._parse_certification_line(line)
            if parsed:
                collected.append(parsed)

        return collected

    def _looks_like_resume_section_heading(self, line: str) -> bool:
        normalized = re.sub(r"[^a-z ]+", " ", line.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        section_headings = {
            "experience",
            "work experience",
            "professional experience",
            "employment history",
            "education",
            "skills",
            "technical skills",
            "summary",
            "profile summary",
            "projects",
            "achievements",
            "languages",
            "personal details",
            "contact",
            "declaration",
        }
        return normalized in section_headings

    def _parse_certification_line(self, line: str) -> Optional[dict]:
        text = line.strip(" \t•-*")
        if not text or len(text) < 3:
            return None

        issuer = ""
        date = ""
        name = text

        month_names = r"(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)"
        date_match = re.search(rf"(?:\b\d{{2}}[/-]\d{{4}}\b|\b{month_names}\s+\d{{4}}\b|\b\d{{4}}\b)\s*$", text, flags=re.IGNORECASE)
        working_text = text
        if date_match:
            date = date_match.group(0).strip()
            working_text = text[:date_match.start()].strip(" ,;-()|")

        parts = [part.strip(" |") for part in re.split(r"\s+-\s+|\s+\|\s+|\s+–\s+|\s+—\s+", working_text) if part.strip(" |")]
        if len(parts) >= 2:
            name = parts[0]
            issuer = parts[1]
        else:
            name = working_text or text

        if not name:
            return None

        return {
            "name": name,
            "issuer": issuer,
            "date": date,
            "credential_id": "",
            "credential_url": "",
        }

    def _clean_certification_name(self, name: str) -> str:
        text = str(name or "").strip()
        if not text:
            return ""

        # Drop metadata-only parenthetical fragments while keeping meaningful short forms like (ACE) or (CKA).
        text = re.sub(
            r"\((?:[^)]*(?:certification|credential|license|licen[cs]e|id|number|no\.?)\s*[:#-]?[^)]*)\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\(([A-Z]{1,10}\d[\w.-]{3,})\)",
            "",
            text,
        )
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

    def _extract_credential_id_from_name(self, name: str) -> str:
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

    def _normalize_certification_key_part(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _canonical_certification_name_key(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\([A-Z0-9.+-]{2,12}\)", "", text)
        text = re.sub(r"\s+", " ", text).strip(" ,;:-")
        return self._normalize_certification_key_part(text)

    def _prefer_certification_name(self, current: str, candidate: str) -> str:
        current = str(current or "").strip()
        candidate = str(candidate or "").strip()
        if not current:
            return candidate
        if not candidate:
            return current

        current_clean = self._clean_certification_name(current)
        candidate_clean = self._clean_certification_name(candidate)

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

    def _prefer_certification_date(self, current: str, candidate: str) -> str:
        current = str(current or "").strip()
        candidate = str(candidate or "").strip()
        if not current:
            return candidate
        if not candidate:
            return current
        # Prefer the more specific date string (e.g. "Jan 2024" over "2024").
        return candidate if len(candidate) > len(current) else current

    def _merge_certifications(self, primary: list[dict], fallback: list[dict]) -> list[dict]:
        merged: list[dict] = []
        key_to_index: dict[str, int] = {}

        for cert in (primary or []) + (fallback or []):
            raw_name = str((cert or {}).get("name") or "").strip()
            name = self._clean_certification_name(raw_name)
            issuer = str((cert or {}).get("issuer") or "").strip()
            date = str((cert or {}).get("date") or "").strip()
            credential_id = str((cert or {}).get("credential_id") or "").strip()
            credential_url = str((cert or {}).get("credential_url") or "").strip()
            if not credential_id:
                credential_id = self._extract_credential_id_from_name(raw_name)
            if not any([name, issuer, date, credential_id, credential_url]):
                continue

            name_key = self._canonical_certification_name_key(name)
            if not name_key:
                continue

            existing_index = key_to_index.get(name_key)
            if existing_index is None:
                merged.append({
                    "name": name,
                    "issuer": issuer,
                    "date": date,
                    "credential_id": credential_id,
                    "credential_url": credential_url,
                })
                key_to_index[name_key] = len(merged) - 1
                continue

            existing = merged[existing_index]
            existing["name"] = self._prefer_certification_name(existing.get("name", ""), name)
            existing["issuer"] = existing.get("issuer", "") or issuer
            existing["date"] = self._prefer_certification_date(existing.get("date", ""), date)
            existing["credential_id"] = existing.get("credential_id", "") or credential_id
            existing["credential_url"] = existing.get("credential_url", "") or credential_url

        return merged

    def _dedupe_certification_models(self, certifications: list) -> list:
        deduped_dicts = self._merge_certifications(
            [
                {
                    "name": getattr(cert, "name", ""),
                    "issuer": getattr(cert, "issuer", ""),
                    "date": getattr(cert, "date", ""),
                    "credential_id": getattr(cert, "credential_id", ""),
                    "credential_url": getattr(cert, "credential_url", ""),
                }
                for cert in (certifications or [])
            ],
            [],
        )
        cert_type = type(certifications[0]) if certifications else None
        if cert_type is None:
            return []
        return [cert_type(**item) for item in deduped_dicts]

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
