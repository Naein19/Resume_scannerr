"""API-level integration test for POST /resumes/from-sheet — proves the
endpoint wires CSV parsing -> Drive download -> the same ingest_resume
pipeline as a direct upload, and that a failed link is reported per-row.
"""

from pathlib import Path
from unittest.mock import patch

from app.schemas.extraction import ExtractedResume

SAMPLE_DRIVE_URL = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrSt/view"
PRIVATE_DRIVE_URL = "https://drive.google.com/file/d/2PrivateFileNotShared/view"

FAKE_EXTRACTED = ExtractedResume(name="Jordan Lee", email="jordan@example.com", skills=["Python"])

_REAL_PDF_BYTES = (
    Path(__file__).parent / "fixtures" / "single_column_resume.pdf"
).read_bytes()


def test_bulk_ingest_from_csv_reports_success_and_failure_per_row(client):
    csv_bytes = f"name,resume_link\nJordan,{SAMPLE_DRIVE_URL}\nPat,{PRIVATE_DRIVE_URL}\n".encode()

    def fake_download(file_id: str):
        if file_id == "1AbCdEfGhIjKlMnOpQrSt":
            return _REAL_PDF_BYTES, "jordan_resume.pdf"
        from app.extraction.sheet_ingest import SheetIngestError

        raise SheetIngestError("Couldn't download file — check that it's shared as 'Anyone with the link can view'.")

    with (
        patch("app.api.resumes.download_drive_file", side_effect=fake_download),
        patch("app.services.resume_service.extract_resume", return_value=FAKE_EXTRACTED),
    ):
        response = client.post(
            "/resumes/from-sheet",
            files={"file": ("links.csv", csv_bytes, "text/csv")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["total_links_found"] == 2

    by_source = {row["source"]: row for row in body["results"]}
    success_row = by_source[SAMPLE_DRIVE_URL]
    assert success_row["status"] == "success"
    assert success_row["resume"]["extraction_status"] == "success"
    assert success_row["resume"]["extracted_data"]["email"] == "jordan@example.com"

    failed_row = by_source[PRIVATE_DRIVE_URL]
    assert failed_row["status"] == "failed"
    assert "shared" in failed_row["error"]
    assert failed_row["resume"] is None


def test_bulk_ingest_rejects_both_file_and_url(client):
    response = client.post(
        "/resumes/from-sheet",
        data={"google_sheet_url": "https://docs.google.com/spreadsheets/d/abc/edit"},
        files={"file": ("links.csv", b"name,link\n", "text/csv")},
    )
    assert response.status_code == 400


def test_bulk_ingest_rejects_neither_file_nor_url(client):
    response = client.post("/resumes/from-sheet")
    assert response.status_code == 400


def test_bulk_ingest_rejects_sheet_with_no_links(client):
    response = client.post(
        "/resumes/from-sheet",
        files={"file": ("links.csv", b"name,email\nJordan,jordan@example.com\n", "text/csv")},
    )
    assert response.status_code == 422
