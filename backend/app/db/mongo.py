"""MongoDB connection, collection names, and index setup.

No ORM and no migration history — MongoDB is schema-less, so the "schema"
is just: these are the collections, these are the indexes that enforce the
invariants we actually care about (uniqueness, fast lookups), and they're
created idempotently at startup instead of via a separate migration tool.
`create_index` is a no-op if an equivalent index already exists, so calling
`ensure_indexes` on every startup is safe and cheap.
"""

from collections.abc import Generator
from typing import Any

from gridfs import GridFSBucket
from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.core.settings import settings

# Every document here is a plain dict — there's no ORM layer translating
# to/from a model class, so `MongoDB = Database[dict[str, Any]]` is the one
# type alias every other module imports instead of repeating the type
# parameter (and satisfying strict mypy's "no bare generics") everywhere.
MongoDB = Database[dict[str, Any]]

CANDIDATES = "candidates"
RESUMES = "resumes"
JOB_DESCRIPTIONS = "job_descriptions"
MATCH_RESULTS = "match_results"

# GridFS stores large binary files (the resume PDFs/text) as two backing
# collections, `{bucket_name}.files` and `{bucket_name}.chunks` — this is
# the "resume_pdfs" bucket visible in Atlas's collection list.
RESUME_PDF_BUCKET = "resume_pdfs"

_client: MongoClient[dict[str, Any]] | None = None


def get_client() -> MongoClient[dict[str, Any]]:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongo_url)
    return _client


def get_database() -> MongoDB:
    return get_client()[settings.db_name]


def get_db() -> Generator[MongoDB, None, None]:
    yield get_database()


def get_resume_bucket(db: MongoDB) -> GridFSBucket:
    return GridFSBucket(db, bucket_name=RESUME_PDF_BUCKET)


def ensure_indexes(db: MongoDB) -> None:
    # sparse=True: email can be null (extraction found no email), and a
    # unique index would otherwise reject every second null.
    db[CANDIDATES].create_index("email", unique=True, sparse=True)

    db[RESUMES].create_index("content_hash", unique=True)
    db[RESUMES].create_index("candidate_id")

    # Leading field matches the shortlist's actual query pattern ("every
    # match result for this job"); the compound index still enforces
    # uniqueness on the (job, candidate) pair regardless of field order.
    db[MATCH_RESULTS].create_index(
        [("job_description_id", ASCENDING), ("candidate_id", ASCENDING)], unique=True
    )
