"""Stage 3 output contract — the LLM judge's verdict for one candidate/JD pair."""

from pydantic import BaseModel, Field


class ScoringResult(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall fit score per the scoring rubric")
    justification: str = Field(
        description="2-4 sentence explanation of the score, referencing specific evidence"
    )
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
