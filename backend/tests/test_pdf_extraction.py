"""PDF text extraction across resume layouts. Operates on bytes, not a
file path — resumes flow through memory + GridFS, never local disk — so
these tests read the fixture files once and pass their bytes.

The "scanned-but-text-layer" case (a resume that's actually an image with
an invisible OCR text layer) can't be honestly reproduced with a
hand-generated fixture — a well-formed OCR'd PDF is not something
pdfplumber and PyMuPDF would disagree on in the first place; the two
libraries only diverge on malformed/unusual PDF structure. What genuinely
needs coverage is the *fallback branch itself*: does the pipeline actually
reach for PyMuPDF and succeed when pdfplumber raises. We test that
directly by forcing a pdfplumber failure on a real, valid fixture and
asserting PyMuPDF still extracts it correctly — that's the code path a
pathological real-world PDF would exercise in production.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.extraction.pdf import TextExtractionError, extract_text, extract_text_from_pdf

FIXTURES = Path(__file__).parent / "fixtures"
SINGLE_COLUMN_BYTES = (FIXTURES / "single_column_resume.pdf").read_bytes()
TWO_COLUMN_BYTES = (FIXTURES / "two_column_resume.pdf").read_bytes()


def test_single_column_resume_extracts_key_content():
    text = extract_text_from_pdf(SINGLE_COLUMN_BYTES)
    assert "John Smith" in text
    assert "john.smith@example.com" in text
    assert "DataCorp" in text
    assert "Python, SQL, Airflow, Kafka, Spark, AWS" in text


def test_two_column_resume_extracts_content_from_both_columns():
    text = extract_text_from_pdf(TWO_COLUMN_BYTES)
    assert "Maria Alvarez" in text
    # Left column
    assert "Product Manager, Northwind" in text
    # Right column
    assert "Product strategy" in text
    assert "B.A. Economics" in text


def test_falls_back_to_pymupdf_when_pdfplumber_fails():
    with patch(
        "app.extraction.pdf._extract_with_pdfplumber",
        side_effect=TextExtractionError("simulated pdfplumber parser failure"),
    ):
        text = extract_text_from_pdf(SINGLE_COLUMN_BYTES)
    assert "John Smith" in text


def test_raises_when_both_parsers_fail():
    with (
        patch(
            "app.extraction.pdf._extract_with_pdfplumber",
            side_effect=TextExtractionError("simulated pdfplumber failure"),
        ),
        patch(
            "app.extraction.pdf._extract_with_pymupdf",
            side_effect=TextExtractionError("simulated pymupdf failure"),
        ),
        pytest.raises(TextExtractionError),
    ):
        extract_text_from_pdf(SINGLE_COLUMN_BYTES)


def test_extract_text_dispatches_on_mime_type():
    content = b"Plain text resume content"
    assert extract_text(content, "text/plain") == "Plain text resume content"


def test_extract_text_rejects_unsupported_mime_type():
    with pytest.raises(ValueError, match="Unsupported mime type"):
        extract_text(b"", "image/png")
