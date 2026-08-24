"""Bulk ingest from a spreadsheet of Google Drive links. Network calls
(fetching a sheet's CSV export, downloading a Drive file) are mocked —
these tests are about the parsing/extraction logic and error handling,
not about Google's actual API behavior.
"""

import io
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from app.extraction.sheet_ingest import (
    SheetIngestError,
    download_drive_file,
    drive_file_ids_from_csv_bytes,
    drive_file_ids_from_xlsx_bytes,
    fetch_drive_file_ids_from_google_sheet,
    find_drive_file_ids,
    google_sheet_csv_export_url,
)

SAMPLE_DRIVE_URL_1 = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrSt/view?usp=sharing"
SAMPLE_DRIVE_URL_2 = "https://drive.google.com/open?id=2ZyXwVuTsRqPoNmLkJiHg"
DUPLICATE_OF_1 = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrSt/view?usp=drive_link"


def test_find_drive_file_ids_extracts_and_dedupes():
    text = f"name,link\nAlice,{SAMPLE_DRIVE_URL_1}\nBob,{SAMPLE_DRIVE_URL_2}\nAlice again,{DUPLICATE_OF_1}"
    ids = find_drive_file_ids(text)
    assert ids == ["1AbCdEfGhIjKlMnOpQrSt", "2ZyXwVuTsRqPoNmLkJiHg"]


def test_find_drive_file_ids_returns_empty_for_no_links():
    assert find_drive_file_ids("name,email\nAlice,alice@example.com") == []


def test_drive_file_ids_from_csv_bytes():
    csv_content = f"name,resume_link\nAlice,{SAMPLE_DRIVE_URL_1}\n".encode()
    assert drive_file_ids_from_csv_bytes(csv_content) == ["1AbCdEfGhIjKlMnOpQrSt"]


def test_drive_file_ids_from_xlsx_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["name", "resume_link"])
    sheet.append(["Alice", SAMPLE_DRIVE_URL_1])
    sheet.append(["Bob", SAMPLE_DRIVE_URL_2])
    buffer = io.BytesIO()
    workbook.save(buffer)

    ids = drive_file_ids_from_xlsx_bytes(buffer.getvalue())
    assert ids == ["1AbCdEfGhIjKlMnOpQrSt", "2ZyXwVuTsRqPoNmLkJiHg"]


def test_drive_file_ids_from_xlsx_bytes_rejects_invalid_file():
    with pytest.raises(SheetIngestError):
        drive_file_ids_from_xlsx_bytes(b"not a real xlsx file")


def test_google_sheet_csv_export_url_extracts_id_and_gid():
    url = "https://docs.google.com/spreadsheets/d/1XyZ_abcSpreadsheetId/edit#gid=42"
    export_url = google_sheet_csv_export_url(url)
    assert export_url == (
        "https://docs.google.com/spreadsheets/d/1XyZ_abcSpreadsheetId/export?format=csv&gid=42"
    )


def test_google_sheet_csv_export_url_defaults_gid_to_zero():
    url = "https://docs.google.com/spreadsheets/d/1XyZ_abcSpreadsheetId/edit"
    export_url = google_sheet_csv_export_url(url)
    assert export_url.endswith("gid=0")


def test_google_sheet_csv_export_url_rejects_non_sheets_url():
    with pytest.raises(SheetIngestError, match="Not a recognizable"):
        google_sheet_csv_export_url("https://example.com/not-a-sheet")


def test_fetch_drive_file_ids_from_google_sheet_parses_csv_response():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/csv"}
    fake_response.text = f"name,link\nAlice,{SAMPLE_DRIVE_URL_1}\n"

    with patch("app.extraction.sheet_ingest.requests.get", return_value=fake_response):
        ids = fetch_drive_file_ids_from_google_sheet(
            "https://docs.google.com/spreadsheets/d/1XyZ/edit"
        )
    assert ids == ["1AbCdEfGhIjKlMnOpQrSt"]


def test_fetch_drive_file_ids_from_google_sheet_rejects_html_response():
    # A private sheet redirects to an HTML sign-in page instead of CSV.
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html; charset=utf-8"}
    fake_response.text = "<html>Sign in to continue</html>"

    with (
        patch("app.extraction.sheet_ingest.requests.get", return_value=fake_response),
        pytest.raises(SheetIngestError, match="Anyone with the link"),
    ):
        fetch_drive_file_ids_from_google_sheet("https://docs.google.com/spreadsheets/d/1XyZ/edit")


def test_download_drive_file_returns_content_and_filename():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {
        "content-type": "application/pdf",
        "content-disposition": 'attachment; filename="resume.pdf"',
    }
    fake_response.content = b"%PDF-1.4 fake pdf bytes"

    with patch("app.extraction.sheet_ingest.requests.get", return_value=fake_response):
        content, filename = download_drive_file("1AbCdEfGhIjKlMnOpQrSt")

    assert content == b"%PDF-1.4 fake pdf bytes"
    assert filename == "resume.pdf"


def test_download_drive_file_rejects_private_file():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html"}
    fake_response.content = b"<html>Access denied</html>"

    with (
        patch("app.extraction.sheet_ingest.requests.get", return_value=fake_response),
        pytest.raises(SheetIngestError, match="check that it's shared"),
    ):
        download_drive_file("private_file_id")
