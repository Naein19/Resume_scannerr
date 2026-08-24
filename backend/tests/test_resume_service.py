"""Integration tests for the resume ingestion pipeline against a real
MongoDB database (see conftest.py). The Claude extraction call itself is
monkeypatched here — these tests are about the *pipeline's* behavior
(caching, dedupe, failure handling), not about extraction quality, which
is covered separately by the live-API tests in test_live_gemini.py.
"""

from unittest.mock import patch

from app.extraction.client import ExtractionFailedError
from app.models.enums import ExtractionStatus
from app.schemas.extraction import ExtractedResume
from app.services.resume_service import ingest_resume

SAMPLE_RESUME_TEXT = b"Jane Doe\njane@example.com\nSkills: Python, FastAPI"

FAKE_EXTRACTED = ExtractedResume(
    name="Jane Doe", email="jane@example.com", skills=["Python", "FastAPI"]
)


def test_ingest_creates_resume_and_candidate(db):
    with patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED):
        resume = ingest_resume(db, SAMPLE_RESUME_TEXT, "jane.txt", "text/plain")

    assert resume["extraction_status"] == ExtractionStatus.SUCCESS.value
    assert resume["extracted_data"]["email"] == "jane@example.com"
    assert resume["candidate_id"] is not None

    candidate = db["candidates"].find_one({"_id": resume["candidate_id"]})
    assert candidate is not None
    assert candidate["email"] == "jane@example.com"
    assert db["candidates"].count_documents({}) == 1


def test_reuploading_identical_bytes_is_a_cache_hit(db):
    with patch(
        "app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED
    ) as mock_extract:
        ingest_resume(db, SAMPLE_RESUME_TEXT, "jane.txt", "text/plain")
        ingest_resume(db, SAMPLE_RESUME_TEXT, "jane_copy.txt", "text/plain")

    # The second call must not invoke the LLM again — that's the whole
    # point of caching by content hash.
    assert mock_extract.call_count == 1
    assert db["resumes"].count_documents({}) == 1


def test_second_candidate_with_same_email_is_deduped(db):
    other_bytes = b"Jane D. - updated resume\njane@example.com"
    with patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED):
        ingest_resume(db, SAMPLE_RESUME_TEXT, "jane_v1.txt", "text/plain")
        ingest_resume(db, other_bytes, "jane_v2.txt", "text/plain")

    assert db["candidates"].count_documents({}) == 1
    assert db["resumes"].count_documents({}) == 2


def test_extraction_failure_is_recorded_not_swallowed(db):
    with patch(
        "app.services.resume_service.extract_resume",
        side_effect=ExtractionFailedError("model never returned a valid tool call"),
    ):
        resume = ingest_resume(db, SAMPLE_RESUME_TEXT, "broken.txt", "text/plain")

    assert resume["extraction_status"] == ExtractionStatus.FAILED.value
    assert "never returned a valid tool call" in resume["extraction_error"]
    assert resume["candidate_id"] is None
