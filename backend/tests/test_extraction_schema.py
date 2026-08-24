"""Stage 1 output contract validation. These tests exercise the Pydantic
model directly — no LLM call — because the contract (null-for-missing,
never guess) is a property of the schema plus the validation call site,
not of any particular model response.
"""

import pytest
from pydantic import ValidationError

from app.schemas.extraction import ExtractedResume


def test_minimal_valid_payload_defaults_lists_to_empty():
    resume = ExtractedResume.model_validate({"name": "Jane Doe"})
    assert resume.name == "Jane Doe"
    assert resume.skills == []
    assert resume.work_history == []
    assert resume.projects == []
    assert resume.education == []
    assert resume.certifications == []
    assert resume.email is None
    assert resume.total_experience_years is None


def test_student_resume_with_projects_and_no_work_history():
    # The common shape for a student/early-career resume: no work_history
    # at all, with projects carrying the real evidence of skill.
    payload = {
        "name": "Alex Kim",
        "skills": ["Python", "React"],
        "projects": [
            {
                "name": "TaskFlow",
                "technologies": ["Next.js", "TypeScript", "Supabase"],
                "description": "A drag-and-drop task board with real-time sync.",
            }
        ],
    }
    resume = ExtractedResume.model_validate(payload)
    assert resume.work_history == []
    assert resume.projects[0].name == "TaskFlow"
    assert resume.projects[0].technologies == ["Next.js", "TypeScript", "Supabase"]


def test_full_payload_round_trips():
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-1234",
        "skills": ["Python", "FastAPI"],
        "total_experience_years": 3.5,
        "work_history": [
            {
                "company": "Acme",
                "title": "Engineer",
                "start": "2021",
                "end": "Present",
                "description": "Built things",
            }
        ],
        "education": [{"degree": "B.S. CS", "institution": "State U", "year": "2020"}],
        "certifications": ["AWS Certified"],
    }
    resume = ExtractedResume.model_validate(payload)
    assert resume.skills == ["Python", "FastAPI"]
    assert resume.work_history[0].company == "Acme"
    assert resume.education[0].degree == "B.S. CS"


def test_wrong_type_for_skills_raises_validation_error():
    with pytest.raises(ValidationError):
        ExtractedResume.model_validate({"skills": "Python, FastAPI"})  # should be a list


def test_extra_unexpected_field_is_ignored_not_rejected():
    # Gemini occasionally adds a field we didn't ask for; the pipeline
    # should tolerate that rather than hard-failing the whole extraction.
    resume = ExtractedResume.model_validate({"name": "Jane", "extra_field": "unexpected"})
    assert resume.name == "Jane"
