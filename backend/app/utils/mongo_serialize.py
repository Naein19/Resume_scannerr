"""Converts between MongoDB's native `ObjectId` and the plain hex strings
the HTTP API deals in. Kept in one place so every route handles a
malformed id the same way (404, not a 500 from a raised `InvalidId`).
"""

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId


def parse_object_id(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except InvalidId:
        return None


def oid_str(value: ObjectId | None) -> str | None:
    return str(value) if value is not None else None


def resume_to_read_dict(resume: dict[str, Any]) -> dict[str, Any]:
    """Maps a raw `resumes` document to the shape ResumeRead expects."""
    return {
        "id": oid_str(resume["_id"]),
        "candidate_id": oid_str(resume.get("candidate_id")),
        "original_filename": resume["original_filename"],
        "extraction_status": resume["extraction_status"],
        "extraction_error": resume.get("extraction_error"),
        "extracted_data": resume.get("extracted_data"),
    }
