import pytest
from pydantic import ValidationError

from app.schemas.scoring import ScoringResult


def test_valid_scoring_result():
    result = ScoringResult.model_validate(
        {
            "score": 8,
            "justification": "Strong overlap in backend skills and seniority.",
            "matched_skills": ["Python", "FastAPI"],
            "missing_skills": ["Kubernetes"],
        }
    )
    assert result.score == 8
    assert result.matched_skills == ["Python", "FastAPI"]


@pytest.mark.parametrize("score", [0, 11, -1, 100])
def test_score_outside_1_to_10_is_rejected(score):
    with pytest.raises(ValidationError):
        ScoringResult.model_validate({"score": score, "justification": "x"})


def test_missing_justification_is_rejected():
    with pytest.raises(ValidationError):
        ScoringResult.model_validate({"score": 5})


def test_skill_lists_default_to_empty():
    result = ScoringResult.model_validate({"score": 5, "justification": "Partial fit."})
    assert result.matched_skills == []
    assert result.missing_skills == []
