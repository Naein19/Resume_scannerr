"""Raw text extraction from an uploaded resume file.

Operates on in-memory bytes, not a file path — resumes are never written
to local disk; they flow straight from the upload/download into GridFS,
and extraction reads the same bytes back out of memory. pdfplumber and
PyMuPDF both accept an in-memory stream natively, so this needs no temp
file.

pdfplumber is primary because its layout-aware text extraction handles
multi-column resumes noticeably better than PyMuPDF's default reading
order. PyMuPDF (fitz) is the fallback for PDFs pdfplumber chokes on —
certain PDF producers (some resume-builder SaaS tools, older Word-to-PDF
exports) emit page structures pdfplumber's parser rejects outright, while
fitz's C-based parser is more permissive.
"""

import io
import logging

import pdfplumber
import pymupdf as fitz

logger = logging.getLogger(__name__)


class TextExtractionError(Exception):
    """Both pdfplumber and the PyMuPDF fallback failed to produce text."""


def extract_text_from_pdf(content: bytes) -> str:
    try:
        return _extract_with_pdfplumber(content)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any
        # pdfplumber failure mode should fall through to the fallback parser
        logger.warning("pdfplumber failed (%s), falling back to PyMuPDF", exc)

    try:
        return _extract_with_pymupdf(content)
    except Exception as exc:
        raise TextExtractionError(
            "Both pdfplumber and PyMuPDF failed to extract text from this PDF"
        ) from exc


def _extract_with_pdfplumber(content: bytes) -> str:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            # layout=True preserves the original whitespace/column
            # positioning (like `pdftotext -layout`) instead of pdfplumber's
            # default of concatenating words in raw reading order, which
            # visibly interleaves text across columns on multi-column
            # resumes. The LLM extraction prompt downstream handles
            # whitespace-delimited columns fine — it's the row-major
            # word-soup from the default mode that loses structure.
            pages.append(page.extract_text(layout=True) or "")
    text = "\n".join(pages).strip()
    if not text:
        raise TextExtractionError("pdfplumber produced no text (likely an image-only scan)")
    return text


def _extract_with_pymupdf(content: bytes) -> str:
    pages: list[str] = []
    # PyMuPDF ships no type stubs, hence the ignore.
    with fitz.open(stream=content, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
        for page in doc:
            pages.append(page.get_text())
    text = "\n".join(pages).strip()
    if not text:
        raise TextExtractionError("PyMuPDF produced no text (likely an image-only scan)")
    return text


def extract_text(content: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return extract_text_from_pdf(content)
    if mime_type == "text/plain":
        return content.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported mime type for text extraction: {mime_type}")
