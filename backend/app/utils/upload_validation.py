"""Upload validation for untrusted files from the public API.

Both checks matter for different reasons: size caps a cost/DoS vector (a
huge file means a huge extraction prompt, i.e. real API spend per upload),
and MIME sniffing via magic bytes closes the trivial bypass of renaming an
.exe to resume.pdf — the browser-supplied Content-Type header and the
filename extension are both attacker-controlled and are not trusted here.
"""

import magic

from app.core.settings import settings


class UploadValidationError(Exception):
    pass


def validate_upload(content: bytes, declared_filename: str) -> str:
    """Returns the sniffed MIME type, or raises UploadValidationError."""
    if len(content) == 0:
        raise UploadValidationError("Uploaded file is empty")

    if len(content) > settings.max_upload_size_bytes:
        raise UploadValidationError(
            f"File exceeds max upload size of {settings.max_upload_size_bytes} bytes"
        )

    sniffed_mime = magic.from_buffer(content, mime=True)
    if sniffed_mime not in settings.allowed_mime_types:
        raise UploadValidationError(
            f"File '{declared_filename}' has content type '{sniffed_mime}', "
            f"which is not one of the allowed types: {settings.allowed_mime_types}"
        )

    return sniffed_mime
