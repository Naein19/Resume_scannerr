"""Orchestrates one resume upload: validate -> hash -> cache check ->
extract text -> Stage 1 LLM extraction -> validate -> persist -> dedupe
into a Candidate. This is the only place that decides "do we need to call
the LLM at all," which is what makes the content-hash cache actually save
money instead of just existing on paper.

Resume bytes are never written to local disk — they go straight into the
`resume_pdfs` GridFS bucket, and text extraction reads the same bytes back
out of memory (app/extraction/pdf.py takes bytes, not a path).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from app.db.mongo import CANDIDATES, RESUMES, MongoDB, get_resume_bucket
from app.extraction.client import ExtractionFailedError, extract_resume
from app.extraction.pdf import TextExtractionError, extract_text
from app.models.enums import ExtractionStatus
from app.utils.hashing import sha256_bytes

logger = logging.getLogger(__name__)


def _find_or_create_candidate(db: MongoDB, extracted: dict[str, Any]) -> dict[str, Any]:
    email = extracted.get("email")
    now = datetime.now(UTC)

    if not email:
        # No email means we can't reliably dedupe; still create a
        # standalone candidate rather than dropping the resume on the floor.
        doc = {
            "name": extracted.get("name"),
            "email": None,
            "phone": extracted.get("phone"),
            "created_at": now,
        }
        doc["_id"] = db[CANDIDATES].insert_one(doc).inserted_id
        return doc

    existing = db[CANDIDATES].find_one({"email": email})
    if existing is None:
        doc = {
            "name": extracted.get("name"),
            "email": email,
            "phone": extracted.get("phone"),
            "created_at": now,
        }
        doc["_id"] = db[CANDIDATES].insert_one(doc).inserted_id
        return doc

    # Keep the candidate record current with their latest resume.
    updates = {k: v for k, v in (("name", extracted.get("name")), ("phone", extracted.get("phone"))) if v}
    if updates:
        db[CANDIDATES].update_one({"_id": existing["_id"]}, {"$set": updates})
        existing.update(updates)
    return existing


def ingest_resume(
    db: MongoDB, content: bytes, original_filename: str, mime_type: str
) -> dict[str, Any]:
    content_hash = sha256_bytes(content)
    cached = db[RESUMES].find_one({"content_hash": content_hash})
    if cached is not None:
        logger.info(
            "Resume %s is a cache hit (hash=%s), skipping extraction",
            original_filename,
            content_hash,
        )
        return cached

    bucket = get_resume_bucket(db)
    file_id = bucket.upload_from_stream(
        original_filename, content, metadata={"mime_type": mime_type}
    )

    now = datetime.now(UTC)
    resume_doc: dict[str, Any] = {
        "candidate_id": None,
        "file_id": file_id,
        "original_filename": original_filename,
        "mime_type": mime_type,
        "content_hash": content_hash,
        "raw_text": None,
        "extracted_data": None,
        "extraction_status": ExtractionStatus.PENDING.value,
        "extraction_error": None,
        "extraction_attempts": 0,
        "created_at": now,
        "updated_at": now,
    }
    resume_doc["_id"] = db[RESUMES].insert_one(resume_doc).inserted_id

    def _fail(error: str, **extra: Any) -> dict[str, Any]:
        update = {
            "extraction_status": ExtractionStatus.FAILED.value,
            "extraction_error": error,
            "updated_at": datetime.now(UTC),
            **extra,
        }
        db[RESUMES].update_one({"_id": resume_doc["_id"]}, {"$set": update})
        resume_doc.update(update)
        return resume_doc

    try:
        raw_text = extract_text(content, mime_type)
    except TextExtractionError as exc:
        return _fail(str(exc))

    try:
        extracted = extract_resume(raw_text)
    except ExtractionFailedError as exc:
        return _fail(str(exc), raw_text=raw_text, extraction_attempts=1)

    extracted_dict = extracted.model_dump(mode="json")
    candidate = _find_or_create_candidate(db, extracted_dict)

    update = {
        "raw_text": raw_text,
        "extraction_attempts": 1,
        "extracted_data": extracted_dict,
        "extraction_status": ExtractionStatus.SUCCESS.value,
        "candidate_id": candidate["_id"],
        "updated_at": datetime.now(UTC),
    }
    db[RESUMES].update_one({"_id": resume_doc["_id"]}, {"$set": update})
    resume_doc.update(update)
    return resume_doc
