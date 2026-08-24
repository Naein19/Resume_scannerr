import logging
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from gridfs.errors import NoFile

from app.core.rate_limit import limiter
from app.db.mongo import RESUMES, MongoDB, get_db, get_resume_bucket
from app.extraction.sheet_ingest import (
    SheetIngestError,
    download_drive_file,
    drive_file_ids_from_csv_bytes,
    drive_file_ids_from_xlsx_bytes,
    fetch_drive_file_ids_from_google_sheet,
)
from app.schemas.api import BulkIngestResponse, BulkIngestRow, ResumeRead
from app.services.resume_service import ingest_resume
from app.utils.mongo_serialize import parse_object_id, resume_to_read_dict
from app.utils.upload_validation import UploadValidationError, validate_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post(
    "",
    response_model=list[ResumeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more resumes for extraction",
    description=(
        "Accepts PDF or plain-text resumes. Each file is validated (size, "
        "sniffed MIME type), hashed for cache lookup, and — on a cache "
        "miss — run through Stage 1 structured extraction. A file that "
        "fails validation or extraction is reported in the response with "
        "its own status rather than failing the whole batch."
    ),
)
@limiter.limit("10/minute")
async def upload_resumes(
    request: Request, files: list[UploadFile] = File(...), db: MongoDB = Depends(get_db)
) -> list[dict[str, Any]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[dict[str, Any]] = []
    for upload in files:
        content = await upload.read()
        try:
            mime_type = validate_upload(content, upload.filename or "unknown")
        except UploadValidationError as exc:
            raise HTTPException(status_code=422, detail=f"{upload.filename}: {exc}") from exc

        resume = ingest_resume(db, content, upload.filename or "unknown", mime_type)
        results.append(resume_to_read_dict(resume))

    return results


@router.post(
    "/from-sheet",
    response_model=BulkIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-upload resumes from a sheet of Google Drive links",
    description=(
        "Accepts either a CSV/XLSX file or a public Google Sheets URL "
        "(shared as 'Anyone with the link can view') containing Google "
        "Drive resume links anywhere in its cells. Every Drive link found "
        "is downloaded and run through the same extraction pipeline as a "
        "direct upload. A link that can't be downloaded (private, "
        "deleted, not actually a Drive file) is reported per-row rather "
        "than failing the whole batch — no Google OAuth is used, so a "
        "private file cannot be read."
    ),
)
@limiter.limit("5/minute")
async def upload_resumes_from_sheet(
    request: Request,
    file: UploadFile | None = File(default=None),
    google_sheet_url: str | None = Form(default=None),
    db: MongoDB = Depends(get_db),
) -> BulkIngestResponse:
    if bool(file) == bool(google_sheet_url):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: a CSV/XLSX file, or a google_sheet_url.",
        )

    try:
        if google_sheet_url is not None:
            file_ids = fetch_drive_file_ids_from_google_sheet(google_sheet_url)
        elif file is not None:
            content = await file.read()
            if (file.filename or "").lower().endswith(".xlsx"):
                file_ids = drive_file_ids_from_xlsx_bytes(content)
            else:
                file_ids = drive_file_ids_from_csv_bytes(content)
        else:
            raise HTTPException(status_code=400, detail="No file or google_sheet_url provided.")
    except SheetIngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not file_ids:
        raise HTTPException(
            status_code=422, detail="No Google Drive links were found in the sheet."
        )

    rows: list[BulkIngestRow] = []
    for file_id in file_ids:
        source_url = f"https://drive.google.com/file/d/{file_id}/view"
        try:
            content, drive_filename = download_drive_file(file_id)
            filename = drive_filename or f"{file_id}.pdf"
            mime_type = validate_upload(content, filename)
            resume = ingest_resume(db, content, filename, mime_type)
            rows.append(
                BulkIngestRow(
                    source=source_url,
                    status="success",
                    resume=ResumeRead.model_validate(resume_to_read_dict(resume)),
                )
            )
        except (SheetIngestError, UploadValidationError) as exc:
            logger.warning("Bulk sheet ingest failed for %s: %s", source_url, exc)
            rows.append(BulkIngestRow(source=source_url, status="failed", error=str(exc)))

    return BulkIngestResponse(total_links_found=len(file_ids), results=rows)


@router.get(
    "/{resume_id}/file",
    summary="Preview the original resume file",
    description=(
        "Streams the resume file out of the resume_pdfs GridFS bucket with "
        "an inline Content-Disposition, so a browser opens/renders it (a "
        "PDF viewer tab) instead of downloading it. Looked up strictly by "
        "the resume's own id and the GridFS file id recorded for it — "
        "never a client-supplied path — so there is no path-traversal "
        "surface here."
    ),
)
async def get_resume_file(resume_id: str, db: MongoDB = Depends(get_db)) -> StreamingResponse:
    oid = parse_object_id(resume_id)
    resume = db[RESUMES].find_one({"_id": oid}) if oid else None
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume file not found")

    bucket = get_resume_bucket(db)
    try:
        grid_out = bucket.open_download_stream(resume["file_id"])
    except NoFile as exc:
        raise HTTPException(status_code=404, detail="Resume file not found") from exc

    def iter_chunks() -> Generator[bytes, None, None]:
        try:
            while chunk := grid_out.read(256 * 1024):
                yield chunk
        finally:
            grid_out.close()

    return StreamingResponse(
        iter_chunks(),
        media_type=resume["mime_type"],
        headers={"Content-Disposition": f'inline; filename="{resume["original_filename"]}"'},
    )
