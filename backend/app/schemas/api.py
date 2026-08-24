"""Request/response DTOs for the HTTP layer. Kept separate from the DB
documents so the API contract can evolve independently of storage, and
separate from the extraction/scoring schemas because those are LLM I/O
contracts, not HTTP contracts — conflating the two would mean a prompt
change and an API breaking change happen in the same edit.

IDs are plain strings, not `uuid.UUID` — MongoDB's native id is an
ObjectId, which serializes to the hex string FastAPI/Pydantic sees here.
The API layer converts `ObjectId` <-> `str` at the boundary (see
`app/utils/mongo_serialize.py`); nothing below this line needs to know
ObjectId exists.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ExtractionStatus
from app.schemas.extraction import ExtractedResume


class JobDescriptionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_text: str = Field(min_length=1)


class JobDescriptionRead(BaseModel):
    id: str
    title: str
    raw_text: str
    created_at: datetime


class ResumeRead(BaseModel):
    id: str
    candidate_id: str | None
    original_filename: str
    extraction_status: ExtractionStatus
    extraction_error: str | None
    extracted_data: ExtractedResume | None


class BulkIngestRow(BaseModel):
    """One row of a bulk sheet-based ingest: either a Drive link resolved
    to a full ResumeRead, or a link that failed (couldn't download, not
    shared publicly, not a valid resume) with a per-row error — the same
    "report per-item, don't fail the whole batch" pattern as /resumes.
    """

    source: str = Field(description="The Google Drive link this row came from")
    status: str = Field(description="'success' or 'failed'")
    resume: ResumeRead | None = None
    error: str | None = None


class BulkIngestResponse(BaseModel):
    total_links_found: int
    results: list[BulkIngestRow]


class MatchRequest(BaseModel):
    candidate_ids: list[str] | None = Field(
        default=None,
        description="Restrict matching to these candidates. Omit to match every candidate with a successfully extracted resume.",
    )


class ShortlistEntry(BaseModel):
    match_result_id: str
    candidate_id: str
    candidate_name: str | None
    candidate_email: str | None
    resume_id: str | None = Field(
        default=None, description="The candidate's resume this match used, for previewing the file"
    )
    stage: str
    embedding_similarity: float | None
    score: float | None
    justification: str | None
    matched_skills: list[str] | None
    missing_skills: list[str] | None


class ShortlistResponse(BaseModel):
    job_description_id: str
    total_candidates: int
    prefiltered_out: int
    scored: int
    results: list[ShortlistEntry]


class DeleteResponse(BaseModel):
    deleted: bool
