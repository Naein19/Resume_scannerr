"""Operations on a candidate as a whole. Currently just permanent
deletion, cascading through their resumes (and the GridFS file each one
owns) and every match result that references them. There is deliberately
no "soft delete" — the feature this exists for is an explicit permanent-
delete action, not a recoverable one.
"""

from bson import ObjectId
from gridfs.errors import NoFile

from app.db.mongo import CANDIDATES, MATCH_RESULTS, RESUMES, MongoDB, get_resume_bucket


def delete_candidate(db: MongoDB, candidate_id: ObjectId) -> bool:
    """Returns False if the candidate didn't exist (nothing to delete)."""
    if db[CANDIDATES].find_one({"_id": candidate_id}) is None:
        return False

    bucket = get_resume_bucket(db)
    for resume in db[RESUMES].find({"candidate_id": candidate_id}, {"file_id": 1}):
        file_id = resume.get("file_id")
        if file_id is None:
            continue
        try:
            bucket.delete(file_id)
        except NoFile:
            pass  # already gone — not fatal to deleting the candidate

    db[RESUMES].delete_many({"candidate_id": candidate_id})
    db[MATCH_RESULTS].delete_many({"candidate_id": candidate_id})
    db[CANDIDATES].delete_one({"_id": candidate_id})
    return True
