"""Regression tests for transient Gemini API failures (503/429).

Found live: a real `/resumes` upload hit a genuine 503 from
`gemini-2.5-flash` ("high demand") and crashed the whole request with an
unhandled 500 instead of retrying or failing that one resume gracefully.
These tests reproduce that failure mode against a mocked client (no need
to wait for a real 503) and assert both fixes: transient errors are
retried before giving up, and giving up raises the same typed error the
callers already handle (`ExtractionFailedError`/`ScoringFailedError`),
not a raw SDK exception.
"""

from unittest.mock import MagicMock

import pytest
from google.genai import errors

from app.extraction.client import ExtractionFailedError, extract_resume
from app.schemas.extraction import ExtractedResume
from app.schemas.scoring import ScoringResult
from app.scoring.client import ScoringFailedError, score_candidate


def _server_error(code: int = 503) -> errors.ServerError:
    return errors.ServerError(
        code, {"error": {"code": code, "message": "overloaded", "status": "UNAVAILABLE"}}, None
    )


def _fake_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


def test_extraction_retries_through_transient_error_then_succeeds():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _server_error(),
        _fake_response('{"name": "Jane Doe", "skills": ["Python"]}'),
    ]

    result = extract_resume("Jane Doe\nSkills: Python", client=client)

    assert result.name == "Jane Doe"
    assert client.models.generate_content.call_count == 2


def test_extraction_gives_up_after_exhausting_retries_and_raises_typed_error():
    client = MagicMock()
    client.models.generate_content.side_effect = _server_error()

    with pytest.raises(ExtractionFailedError, match="Gemini API error"):
        extract_resume("Jane Doe\nSkills: Python", client=client)

    # stop_after_attempt(3): exhausting the transient-error retry budget
    # raises ExtractionFailedError immediately rather than falling through
    # to the outer self-correction loop — a persistent 503 isn't something
    # a corrected prompt would fix, so a second outer attempt would just
    # burn another 3 calls for no reason.
    assert client.models.generate_content.call_count == 3


def test_scoring_retries_through_transient_error_then_succeeds():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _server_error(429),
        _fake_response('{"score": 7, "justification": "Solid match."}'),
    ]

    result = score_candidate(ExtractedResume(name="Jane"), "Backend role", client=client)

    assert isinstance(result, ScoringResult)
    assert result.score == 7


def test_scoring_gives_up_after_exhausting_retries_and_raises_typed_error():
    client = MagicMock()
    client.models.generate_content.side_effect = _server_error()

    with pytest.raises(ScoringFailedError, match="Gemini API error"):
        score_candidate(ExtractedResume(name="Jane"), "Backend role", client=client)
