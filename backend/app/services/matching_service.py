"""Orchestrates the full two-stage matching run for one job description:
embedding pre-filter (Stage 2) first, LLM judge (Stage 3) only for
candidates that pass it. This module is the reason the pre-filter is a
real cost/quota control and not decoration — a candidate that fails Stage
2 never reaches `score_candidate`, the only Gemini call in the whole
pipeline at match time (extraction happens once, at upload time, and is
cached thereafter).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app.db.mongo import CANDIDATES, MATCH_RESULTS, RESUMES, MongoDB
from app.embeddings.similarity import (
    candidate_profile_to_text,
    cosine_similarity,
    passes_prefilter,
)
from app.models.enums import ExtractionStatus, MatchStage
from app.schemas.extraction import ExtractedResume
from app.scoring.client import ScoringFailedError, score_candidate

logger = logging.getLogger(__name__)


def latest_successful_resume(db: MongoDB, candidate_id: ObjectId) -> dict[str, Any] | None:
    """Public — also used by the shortlist endpoint (app/api/jobs.py) to
    resolve which resume file a match result's "view resume" link should
    point to, so both call sites agree on what "the candidate's resume"
    means without duplicating the lookup.
    """
    return db[RESUMES].find_one(
        {"candidate_id": candidate_id, "extraction_status": ExtractionStatus.SUCCESS.value},
        sort=[("created_at", -1)],
    )


def _eligible_candidates(
    db: MongoDB, candidate_ids: list[ObjectId] | None
) -> list[dict[str, Any]]:
    ids_with_resumes = {
        cid
        for cid in db[RESUMES].distinct(
            "candidate_id", {"extraction_status": ExtractionStatus.SUCCESS.value}
        )
        if cid is not None
    }
    if candidate_ids is not None:
        ids_with_resumes &= set(candidate_ids)
    return list(db[CANDIDATES].find({"_id": {"$in": list(ids_with_resumes)}}))


def _upsert_match_result(
    db: MongoDB, candidate_id: ObjectId, job_description_id: ObjectId, **fields: Any
) -> dict[str, Any]:
    result = db[MATCH_RESULTS].find_one_and_update(
        {"candidate_id": candidate_id, "job_description_id": job_description_id},
        {"$set": fields, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    assert result is not None  # upsert=True guarantees a document comes back
    return result


def run_matching(
    db: MongoDB, job: dict[str, Any], candidate_ids: list[ObjectId] | None = None
) -> list[dict[str, Any]]:
    candidates = _eligible_candidates(db, candidate_ids)
    results: list[dict[str, Any]] = []

    for candidate in candidates:
        resume = latest_successful_resume(db, candidate["_id"])
        if resume is None or resume.get("extracted_data") is None:
            continue

        profile = ExtractedResume.model_validate(resume["extracted_data"])
        similarity = cosine_similarity(
            candidate_profile_to_text(profile), job["raw_text"]
        )

        if not passes_prefilter(similarity):
            result = _upsert_match_result(
                db,
                candidate["_id"],
                job["_id"],
                stage=MatchStage.PREFILTERED_OUT.value,
                embedding_similarity=similarity,
                score=None,
                justification=None,
                matched_skills=None,
                missing_skills=None,
            )
            results.append(result)
            continue

        try:
            verdict = score_candidate(profile, job["raw_text"])
        except ScoringFailedError as exc:
            logger.error(
                "Scoring failed for candidate %s / jd %s: %s", candidate["_id"], job["_id"], exc
            )
            continue

        result = _upsert_match_result(
            db,
            candidate["_id"],
            job["_id"],
            stage=MatchStage.SCORED.value,
            embedding_similarity=similarity,
            score=verdict.score,
            justification=verdict.justification,
            matched_skills=verdict.matched_skills,
            missing_skills=verdict.missing_skills,
        )
        results.append(result)

    return results
