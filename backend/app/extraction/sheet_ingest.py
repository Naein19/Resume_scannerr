"""Bulk resume ingestion from a spreadsheet of Google Drive links: a
CSV/XLSX upload, or a pasted Google Sheets URL read via its public CSV
export (`.../export?format=csv`) — the same trick any tool uses to read a
publicly-shared sheet without Google API credentials, since it's just an
HTTP GET against a URL Sheets already serves for "download as CSV."

SSRF note: every URL this module fetches is one *we construct*, from a
Drive/Sheets file ID we extracted via regex — never the raw URL a user
pasted, passed straight to `requests.get`. That's a stronger guarantee
than a host allowlist on user input: there is no code path here that can
fetch an arbitrary attacker-chosen URL, only a `drive.google.com` or
`docs.google.com` URL built from an ID.
"""

import io
import re
import zipfile

import openpyxl
import requests
from openpyxl.utils.exceptions import InvalidFileException

_DRIVE_FILE_ID_PATTERN = re.compile(
    r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9_-]{10,})"
)
_SHEETS_ID_PATTERN = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)")
_GID_PATTERN = re.compile(r"[#&?]gid=(\d+)")

_REQUEST_TIMEOUT_SECONDS = 20


class SheetIngestError(Exception):
    """A sheet or a linked file couldn't be read. Always carries a
    user-facing message — "check sharing permissions" for anything that
    smells like Google's access-denied/HTML-interstitial response, since
    we deliberately don't build an OAuth flow to handle private files.
    """


def find_drive_file_ids(text: str) -> list[str]:
    """Unique Drive file IDs found anywhere in the text, first-seen order."""
    return list(dict.fromkeys(m.group(1) for m in _DRIVE_FILE_ID_PATTERN.finditer(text)))


def drive_file_ids_from_csv_bytes(content: bytes) -> list[str]:
    return find_drive_file_ids(content.decode("utf-8", errors="replace"))


def drive_file_ids_from_xlsx_bytes(content: bytes) -> list[str]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError) as exc:
        # .xlsx is a zip archive under the hood — a non-.xlsx or corrupt
        # file fails at the zip layer (BadZipFile) or partway through
        # reading the archive's expected internal structure (KeyError),
        # not always at openpyxl's own format-check layer.
        raise SheetIngestError(f"Not a valid .xlsx file: {exc}") from exc

    cell_texts = [
        str(cell)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows(values_only=True)
        for cell in row
        if cell is not None
    ]
    return find_drive_file_ids("\n".join(cell_texts))


def google_sheet_csv_export_url(sheet_url: str) -> str:
    match = _SHEETS_ID_PATTERN.search(sheet_url)
    if not match:
        raise SheetIngestError(f"Not a recognizable Google Sheets URL: {sheet_url}")
    spreadsheet_id = match.group(1)
    gid_match = _GID_PATTERN.search(sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


def fetch_drive_file_ids_from_google_sheet(sheet_url: str) -> list[str]:
    export_url = google_sheet_csv_export_url(sheet_url)
    try:
        response = requests.get(export_url, timeout=_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise SheetIngestError(f"Couldn't reach Google Sheets: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "text/html" in content_type:
        # A non-public sheet redirects to an HTML sign-in/access page
        # instead of serving CSV — this is Google's own signal that we
        # can't read it without the OAuth flow we deliberately skipped.
        raise SheetIngestError(
            "Couldn't read this Google Sheet — make sure it's shared as "
            "'Anyone with the link can view'."
        )
    return find_drive_file_ids(response.text)


def download_drive_file(file_id: str) -> tuple[bytes, str | None]:
    """Returns (content, filename). filename is None when Google's
    response doesn't include one (Content-Disposition is only present for
    small enough files it serves directly, without the download-warning
    interstitial).
    """
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise SheetIngestError(f"Couldn't reach Google Drive: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "text/html" in content_type:
        raise SheetIngestError(
            f"Couldn't download file {file_id} — check that it's shared as "
            "'Anyone with the link can view'."
        )

    filename = None
    disposition = response.headers.get("content-disposition", "")
    if (match := re.search(r'filename="([^"]+)"', disposition)) is not None:
        filename = match.group(1)

    return response.content, filename
