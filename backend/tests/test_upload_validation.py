import pytest

from app.utils.upload_validation import UploadValidationError, validate_upload

PDF_MAGIC_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
EXE_MAGIC_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"


def test_valid_pdf_passes():
    assert validate_upload(PDF_MAGIC_BYTES, "resume.pdf") == "application/pdf"


def test_valid_plain_text_passes():
    assert validate_upload(b"Jane Doe\nSoftware Engineer\n", "resume.txt") == "text/plain"


def test_empty_file_rejected():
    with pytest.raises(UploadValidationError, match="empty"):
        validate_upload(b"", "resume.pdf")


def test_oversized_file_rejected():
    huge = b"a" * (6 * 1024 * 1024)
    with pytest.raises(UploadValidationError, match="max upload size"):
        validate_upload(huge, "resume.txt")


def test_disguised_executable_rejected_despite_pdf_extension():
    # The whole point of magic-byte sniffing: renaming a binary to
    # "resume.pdf" must not be enough to get it past validation.
    with pytest.raises(UploadValidationError, match="content type"):
        validate_upload(EXE_MAGIC_BYTES, "resume.pdf")
