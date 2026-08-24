from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.rate_limit import limiter
from app.db.mongo import MongoDB, get_db
from app.schemas.api import DeleteResponse
from app.services.candidate_service import delete_candidate
from app.utils.mongo_serialize import parse_object_id

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.delete(
    "/{candidate_id}",
    response_model=DeleteResponse,
    summary="Permanently delete a candidate",
    description=(
        "Deletes the candidate, every resume they have on file (including "
        "the underlying GridFS PDF/text), and every match result that "
        "references them. This is not reversible — there is no soft "
        "delete or trash."
    ),
)
@limiter.limit("20/minute")
async def delete_candidate_route(
    request: Request, candidate_id: str, db: MongoDB = Depends(get_db)
) -> DeleteResponse:
    oid = parse_object_id(candidate_id)
    if oid is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    deleted = delete_candidate(db, oid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return DeleteResponse(deleted=True)
