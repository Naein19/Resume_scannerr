"""Full pipeline integration test, driven entirely through the HTTP API:
create a JD, upload a resume, run matching, fetch the shortlist, delete
the candidate. This is the test that proves the pieces are wired together
correctly end-to-end, not just individually correct. Stage 1 and Stage 3
LLM calls are mocked at their call sites (this test is about pipeline
wiring and output shape, not LLM output quality — see
test_live_gemini.py for a real-API test).
"""

from unittest.mock import patch

from app.schemas.extraction import ExtractedResume
from app.schemas.scoring import ScoringResult

FAKE_EXTRACTED = ExtractedResume(
    name="Alex Rivera",
    email="alex.rivera@example.com",
    skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
    total_experience_years=4.0,
)

FAKE_VERDICT = ScoringResult(
    score=8,
    justification="Strong overlap on Python/FastAPI/PostgreSQL with 4 years of relevant experience.",
    matched_skills=["Python", "FastAPI", "PostgreSQL"],
    missing_skills=["Kubernetes"],
)


def test_full_pipeline_end_to_end(client):
    jd_response = client.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "raw_text": "We need a backend engineer skilled in Python, FastAPI, PostgreSQL, and Kubernetes.",
        },
    )
    assert jd_response.status_code == 201
    job_id = jd_response.json()["id"]

    with patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED):
        upload_response = client.post(
            "/resumes",
            files={"files": ("alex.txt", b"Alex Rivera resume text", "text/plain")},
        )
    assert upload_response.status_code == 201
    resume_payload = upload_response.json()[0]
    assert resume_payload["extraction_status"] == "success"
    assert resume_payload["extracted_data"]["email"] == "alex.rivera@example.com"

    with patch("app.services.matching_service.score_candidate", return_value=FAKE_VERDICT):
        match_response = client.post(f"/jobs/{job_id}/match", json={})
    assert match_response.status_code == 200
    match_body = match_response.json()

    # --- shortlist output shape ---
    assert match_body["job_description_id"] == job_id
    assert match_body["total_candidates"] == 1
    assert match_body["scored"] == 1
    assert match_body["prefiltered_out"] == 0
    assert len(match_body["results"]) == 1

    entry = match_body["results"][0]
    assert entry["candidate_email"] == "alex.rivera@example.com"
    assert entry["stage"] == "scored"
    assert entry["score"] == 8
    assert set(entry["matched_skills"]) == {"Python", "FastAPI", "PostgreSQL"}
    assert entry["missing_skills"] == ["Kubernetes"]
    assert "Strong overlap" in entry["justification"]
    assert entry["resume_id"] == resume_payload["id"]

    shortlist_response = client.get(f"/jobs/{job_id}/shortlist")
    assert shortlist_response.status_code == 200
    assert shortlist_response.json() == match_body

    # --- resume file preview (served from GridFS) ---
    file_response = client.get(f"/resumes/{entry['resume_id']}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"Alex Rivera resume text"
    assert file_response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "inline" in file_response.headers["content-disposition"]

    # --- permanent delete ---
    delete_response = client.delete(f"/candidates/{entry['candidate_id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    # The resume file, and the match result, are gone with it.
    assert client.get(f"/resumes/{entry['resume_id']}/file").status_code == 404
    shortlist_after_delete = client.get(f"/jobs/{job_id}/shortlist").json()
    assert shortlist_after_delete["total_candidates"] == 0

    # Deleting again reports 404 rather than silently succeeding twice.
    assert client.delete(f"/candidates/{entry['candidate_id']}").status_code == 404


def test_match_only_includes_requested_candidate_ids(client):
    """Regression test: omitting candidate_ids used to match every
    candidate ever ingested by anyone, including unrelated ones from a
    different upload batch — not just the ones the caller uploaded.
    """
    jd_response = client.post(
        "/jobs", json={"title": "Backend Engineer", "raw_text": "Python and FastAPI."}
    )
    job_id = jd_response.json()["id"]

    with patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED):
        included = client.post(
            "/resumes", files={"files": ("alex.txt", b"Alex Rivera resume text", "text/plain")}
        ).json()[0]

    other_extracted = ExtractedResume(
        name="Someone Else", email="someone.else@example.com", skills=["Python"]
    )
    with patch("app.services.resume_service.extract_resume", return_value=other_extracted):
        client.post(
            "/resumes", files={"files": ("other.txt", b"Someone Else resume text", "text/plain")}
        )

    with patch("app.services.matching_service.score_candidate", return_value=FAKE_VERDICT):
        response = client.post(
            f"/jobs/{job_id}/match", json={"candidate_ids": [included["candidate_id"]]}
        )

    body = response.json()
    assert body["total_candidates"] == 1
    assert body["results"][0]["candidate_email"] == "alex.rivera@example.com"


def test_resume_file_returns_404_for_unknown_id(client):
    response = client.get("/resumes/000000000000000000000000/file")
    assert response.status_code == 404


def test_delete_candidate_returns_404_for_unknown_id(client):
    response = client.delete("/candidates/000000000000000000000000")
    assert response.status_code == 404


def test_upload_rejects_disguised_executable(client):
    exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"

    response = client.post("/resumes", files={"files": ("resume.pdf", exe_bytes, "application/pdf")})
    assert response.status_code == 422


def test_match_against_nonexistent_job_returns_404(client):
    response = client.post("/jobs/000000000000000000000000/match", json={})
    assert response.status_code == 404


def test_delete_job_removes_it_and_its_match_results(client):
    jd_response = client.post(
        "/jobs", json={"title": "Backend Engineer", "raw_text": "Python and FastAPI."}
    )
    job_id = jd_response.json()["id"]

    with patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED):
        client.post(
            "/resumes", files={"files": ("alex.txt", b"Alex Rivera resume text", "text/plain")}
        )
    with patch("app.services.matching_service.score_candidate", return_value=FAKE_VERDICT):
        client.post(f"/jobs/{job_id}/match", json={})

    delete_response = client.delete(f"/jobs/{job_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    assert client.get(f"/jobs/{job_id}/shortlist").status_code == 404
    assert client.delete(f"/jobs/{job_id}").status_code == 404
