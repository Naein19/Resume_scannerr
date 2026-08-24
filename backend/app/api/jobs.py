from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.db.mongo import CANDIDATES, JOB_DESCRIPTIONS, MATCH_RESULTS, MongoDB, get_db
from app.models.enums import MatchStage
from app.schemas.api import (
    DeleteResponse,
    JobDescriptionCreate,
    JobDescriptionRead,
    MatchRequest,
    ShortlistEntry,
    ShortlistResponse,
)
from app.services.matching_service import latest_successful_resume, run_matching
from app.utils.mongo_serialize import oid_str, parse_object_id

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job_or_404(db: MongoDB, job_id: str) -> dict[str, Any]:
    oid = parse_object_id(job_id)
    job = db[JOB_DESCRIPTIONS].find_one({"_id": oid}) if oid else None
    if job is None:
        raise HTTPException(status_code=404, detail="Job description not found")
    return job


@router.post(
    "",
    response_model=JobDescriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job description",
    description="Stores a job description's raw text, to be matched against candidates later.",
)
@limiter.limit("30/minute")
async def create_job(
    request: Request, payload: JobDescriptionCreate, db: MongoDB = Depends(get_db)
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "title": payload.title,
        "raw_text": payload.raw_text,
        "created_at": datetime.now(UTC),
    }
    doc["_id"] = db[JOB_DESCRIPTIONS].insert_one(doc).inserted_id
    return {**doc, "id": oid_str(doc["_id"])}


@router.post(
    "/{job_id}/match",
    response_model=ShortlistResponse,
    summary="Run two-stage matching against candidates",
    description=(
        "Runs the embedding pre-filter (Stage 2) against every candidate "
        "with a successfully extracted resume, then the LLM judge (Stage 3) "
        "only for those that pass the similarity threshold. Idempotent per "
        "candidate/JD pair — re-running overwrites that pair's prior result "
        "rather than duplicating it."
    ),
)
@limiter.limit("5/minute")
async def match_job(
    request: Request, job_id: str, payload: MatchRequest, db: MongoDB = Depends(get_db)
) -> ShortlistResponse:
    job = _get_job_or_404(db, job_id)

    candidate_oids: list[ObjectId] | None = None
    if payload.candidate_ids is not None:
        candidate_oids = [
            oid for cid in payload.candidate_ids if (oid := parse_object_id(cid)) is not None
        ]

    results = run_matching(db, job, candidate_oids)
    return _build_shortlist_response(db, job["_id"], results)


@router.get(
    "/{job_id}/shortlist",
    response_model=ShortlistResponse,
    summary="Get the ranked shortlist for a job",
    description="Returns every match result computed so far for this job, ranked by score descending, prefiltered candidates last.",
)
async def get_shortlist(
    request: Request, job_id: str, db: MongoDB = Depends(get_db)
) -> ShortlistResponse:
    job = _get_job_or_404(db, job_id)
    results = list(db[MATCH_RESULTS].find({"job_description_id": job["_id"]}))
    return _build_shortlist_response(db, job["_id"], results)


@router.delete(
    "/{job_id}",
    response_model=DeleteResponse,
    summary="Permanently delete a job description",
    description="Deletes the job description and every match result computed against it. Not reversible.",
)
@limiter.limit("20/minute")
async def delete_job(
    request: Request, job_id: str, db: MongoDB = Depends(get_db)
) -> DeleteResponse:
    job = _get_job_or_404(db, job_id)
    db[MATCH_RESULTS].delete_many({"job_description_id": job["_id"]})
    db[JOB_DESCRIPTIONS].delete_one({"_id": job["_id"]})
    return DeleteResponse(deleted=True)


def _build_shortlist_response(
    db: MongoDB, job_id: ObjectId, results: list[dict[str, Any]]
) -> ShortlistResponse:
    entries = []
    for r in results:
        candidate = db[CANDIDATES].find_one({"_id": r["candidate_id"]})
        resume = latest_successful_resume(db, r["candidate_id"])
        entries.append(
            ShortlistEntry(
                match_result_id=oid_str(r["_id"]) or "",
                candidate_id=oid_str(r["candidate_id"]) or "",
                candidate_name=candidate.get("name") if candidate else None,
                candidate_email=candidate.get("email") if candidate else None,
                resume_id=oid_str(resume["_id"]) if resume else None,
                stage=r["stage"],
                embedding_similarity=r.get("embedding_similarity"),
                score=r.get("score"),
                justification=r.get("justification"),
                matched_skills=r.get("matched_skills"),
                missing_skills=r.get("missing_skills"),
            )
        )
    entries.sort(key=lambda e: (e.score is None, -(e.score or 0)))

    return ShortlistResponse(
        job_description_id=oid_str(job_id) or "",
        total_candidates=len(entries),
        prefiltered_out=sum(1 for e in entries if e.stage == MatchStage.PREFILTERED_OUT.value),
        scored=sum(1 for e in entries if e.stage == MatchStage.SCORED.value),
        results=entries,
    )
