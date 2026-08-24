"""Stage 1 output contract.

This model is the single source of truth for what "a parsed resume" means —
it's used three ways: (1) converted to the JSON schema handed to Gemini as
`response_json_schema`, so the model can't return anything outside this
shape; (2) the target of validation when the response comes back; (3) the
shape stored in `resumes.extracted_data`. One model, three uses, no drift
between "what we asked for" and "what we store."
"""

from pydantic import BaseModel, Field


class WorkHistoryEntry(BaseModel):
    company: str | None = Field(default=None, description="Employer name")
    title: str | None = Field(default=None, description="Job title held")
    start: str | None = Field(default=None, description="Start date, as written on the resume")
    end: str | None = Field(
        default=None, description="End date, as written on the resume, or 'Present'"
    )
    description: str | None = Field(
        default=None, description="Summary of responsibilities/achievements in this role"
    )


class EducationEntry(BaseModel):
    degree: str | None = Field(default=None)
    institution: str | None = Field(default=None)
    year: str | None = Field(default=None, description="Graduation year, as written")


class ProjectEntry(BaseModel):
    """A project the candidate built — the dominant experience section on
    student/early-career resumes, which often have no `work_history` at
    all. Without this field, a candidate's most concrete evidence of
    skill (what they actually built, and with what) would be invisible to
    Stage 3 beyond whatever bled into the flat `skills` list — discovered
    by testing extraction against a real student resume with three
    substantial projects and zero formal work history.
    """

    name: str | None = Field(default=None, description="Project name/title")
    technologies: list[str] = Field(
        default_factory=list, description="Technologies/tools used, as named on the resume"
    )
    description: str | None = Field(
        default=None, description="What the project does and/or the candidate's role in it"
    )


class ExtractedResume(BaseModel):
    """Structured facts pulled from a single resume. Every field is
    optional because a resume that omits a field must yield `null`, not a
    guess — the extraction prompt is explicit about this and Stage 3 relies
    on it (a fabricated skill would silently inflate a match score)."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = Field(default_factory=list)
    total_experience_years: float | None = Field(
        default=None, description="Total professional experience in years, estimated from work history"
    )
    work_history: list[WorkHistoryEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
