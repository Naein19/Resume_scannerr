"""Integration test for the full match orchestration against real MongoDB.
Embeddings run for real (fast, local, no API cost) — only the Stage 3
Gemini call is mocked, since the point here is proving the pipeline wires
Stage 2 -> Stage 3 correctly, not re-testing prompt quality.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from app.models.enums import ExtractionStatus, MatchStage
from app.schemas.extraction import ExtractedResume, ProjectEntry
from app.schemas.scoring import ScoringResult
from app.services.matching_service import run_matching


def _make_candidate_with_resume(db, *, email: str, skills: list[str], projects=None) -> dict:
    profile = ExtractedResume(
        name=email.split("@")[0], email=email, skills=skills, projects=projects or []
    )
    candidate = {"name": profile.name, "email": email, "created_at": datetime.now(UTC)}
    candidate["_id"] = db["candidates"].insert_one(candidate).inserted_id

    resume = {
        "candidate_id": candidate["_id"],
        "file_id": None,
        "original_filename": f"{email}.txt",
        "mime_type": "text/plain",
        "content_hash": email,
        "extracted_data": profile.model_dump(mode="json"),
        "extraction_status": ExtractionStatus.SUCCESS.value,
        "extraction_error": None,
        "extraction_attempts": 1,
        "raw_text": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    db["resumes"].insert_one(resume)
    return candidate


def test_relevant_candidate_is_scored_and_irrelevant_is_prefiltered(db):
    jd = {
        "title": "Backend Engineer",
        "raw_text": "Looking for a backend engineer with Python, FastAPI, and PostgreSQL experience.",
        "created_at": datetime.now(UTC),
    }
    jd["_id"] = db["job_descriptions"].insert_one(jd).inserted_id

    relevant = _make_candidate_with_resume(
        db, email="relevant@example.com", skills=["Python", "FastAPI", "PostgreSQL"]
    )
    irrelevant = _make_candidate_with_resume(
        db,
        email="irrelevant@example.com",
        skills=["Watercolor painting", "Baking", "Landscape gardening"],
    )

    fake_verdict = ScoringResult(
        score=9,
        justification="Direct skill match on Python, FastAPI, and PostgreSQL.",
        matched_skills=["Python", "FastAPI", "PostgreSQL"],
        missing_skills=[],
    )
    with patch(
        "app.services.matching_service.score_candidate", return_value=fake_verdict
    ) as mock_score:
        results = run_matching(db, jd)

    by_candidate = {r["candidate_id"]: r for r in results}

    relevant_result = by_candidate[relevant["_id"]]
    assert relevant_result["stage"] == MatchStage.SCORED.value
    assert relevant_result["score"] == 9
    assert relevant_result["matched_skills"] == ["Python", "FastAPI", "PostgreSQL"]

    irrelevant_result = by_candidate[irrelevant["_id"]]
    assert irrelevant_result["stage"] == MatchStage.PREFILTERED_OUT.value
    assert irrelevant_result["score"] is None

    # The LLM judge must only be called for the candidate that passed the
    # embedding pre-filter — this is the cost optimization the whole
    # two-stage design exists for.
    assert mock_score.call_count == 1


def test_rerunning_match_overwrites_not_duplicates(db):
    jd = {
        "title": "Backend Engineer",
        "raw_text": "Python and FastAPI backend role.",
        "created_at": datetime.now(UTC),
    }
    jd["_id"] = db["job_descriptions"].insert_one(jd).inserted_id
    candidate = _make_candidate_with_resume(
        db, email="repeat@example.com", skills=["Python", "FastAPI"]
    )

    fake_verdict = ScoringResult(score=7, justification="Good fit.", matched_skills=["Python"])
    with patch("app.services.matching_service.score_candidate", return_value=fake_verdict):
        run_matching(db, jd)
        results = run_matching(db, jd, candidate_ids=[candidate["_id"]])

    assert len(results) == 1
    assert db["match_results"].count_documents({}) == 1


def test_project_heavy_student_candidate_passes_prefilter(db):
    """Regression test for a real bug found testing against an actual
    student resume: several verbose project descriptions diluted the
    embedding signal enough to drop a genuinely relevant candidate below
    the default threshold (0.53 -> 0.28 in the live repro). This resume
    shape — no work history, three substantial projects with paragraph
    descriptions, skills that clearly match the JD — must still pass.
    """
    jd = {
        "title": "Software Engineer Intern",
        "raw_text": (
            "We are looking for a Software Engineer Intern. Ideal candidates have "
            "experience with Python or Java, data structures and algorithms, and "
            "some exposure to web development (React, Node, or similar) or machine "
            "learning. Strong problem-solving skills and coursework in computer "
            "science required."
        ),
        "created_at": datetime.now(UTC),
    }
    jd["_id"] = db["job_descriptions"].insert_one(jd).inserted_id

    candidate = _make_candidate_with_resume(
        db,
        email="student@example.com",
        skills=[
            "Java", "Python", "JavaScript", "TypeScript", "React.js", "Next.js",
            "Node.js", "REST APIs", "PostgreSQL", "Git", "Data Structures & Algorithms",
        ],
        projects=[
            ProjectEntry(
                name="PYQS Hub",
                technologies=["Next.js", "TypeScript", "Supabase", "PostgreSQL"],
                description=(
                    "Built a platform to organize and access previous year question "
                    "papers with search and filtering. Reached 500+ users in 3 days "
                    "with 60-100 daily active users. Designed backend using Supabase "
                    "and PostgreSQL for efficient data retrieval. Implemented "
                    "mobile-first UI for consistent performance across devices."
                ),
            ),
            ProjectEntry(
                name="FormFlow",
                technologies=["Next.js", "TypeScript", "Tailwind", "Generative AI"],
                description=(
                    "Built drag-and-drop form builder using dnd-kit and TypeScript. "
                    "Integrated AI to generate forms from natural language input. "
                    "Developed analytics dashboard to track submissions and usage."
                ),
            ),
            ProjectEntry(
                name="GenAI Voice Assistant",
                technologies=["Python", "Gemini AI", "LiveKit"],
                description=(
                    "Built real-time voice assistant with modular backend "
                    "architecture. Integrated APIs for search, weather, and email "
                    "automation. Designed system for low-latency interaction using "
                    "LiveKit."
                ),
            ),
        ],
    )

    fake_verdict = ScoringResult(score=9, justification="Strong match.", matched_skills=["Python"])
    with patch("app.services.matching_service.score_candidate", return_value=fake_verdict):
        results = run_matching(db, jd)

    result = next(r for r in results if r["candidate_id"] == candidate["_id"])
    assert result["stage"] == MatchStage.SCORED.value
    assert result["embedding_similarity"] is not None
    assert result["embedding_similarity"] >= 0.35
