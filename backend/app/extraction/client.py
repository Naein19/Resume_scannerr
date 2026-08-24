"""Stage 1: turn raw resume text into a validated `ExtractedResume` via a
single Gemini structured-output call, with one self-correction retry on
validation failure.

Structured output via `response_mime_type="application/json"` +
`response_json_schema`, not "return JSON" in free text: the API constrains
the token generation itself to match our schema, which removes an entire
class of failure (prose wrapped around the JSON, trailing commas, markdown
fences) that free-text JSON prompting is prone to. We still run the result
through Pydantic ourselves rather than trusting the API's guarantee blindly
— schema-constrained decoding enforces *shape*, not business rules like
"score must reflect the rubric," and defense in depth is cheap here.
"""

import logging

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.core.audit_log import log_llm_call
from app.core.gemini_pool import call_with_key_rotation
from app.core.gemini_retry import retry_transient_gemini_errors
from app.core.settings import settings
from app.schemas.extraction import ExtractedResume
from prompts import extraction_v1

logger = logging.getLogger(__name__)

_RESPONSE_SCHEMA = ExtractedResume.model_json_schema()


class ExtractionFailedError(Exception):
    """Raised when extraction fails validation even after the retry. This
    is allowed to propagate — a resume we can't parse should surface as a
    visible failure (`resumes.extraction_status = FAILED`), never a
    silently empty candidate profile that then scores as a bad fit for
    every job.
    """


@retry_transient_gemini_errors
def _call_gemini(client: genai.Client, system_instruction: str, user_message: str) -> types.GenerateContentResponse:
    return client.models.generate_content(
        model=settings.gemini_extraction_model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=_RESPONSE_SCHEMA,
        ),
    )


def extract_resume(resume_text: str, client: genai.Client | None = None) -> ExtractedResume:
    system_prompt = extraction_v1.build_system_prompt()
    user_message = extraction_v1.build_user_message(resume_text)

    last_error: Exception | None = None
    for attempt in range(1, settings.gemini_max_retries + 2):
        message = (
            user_message
            if attempt == 1
            else extraction_v1.build_retry_message(resume_text, str(last_error))
        )

        def _make_call(c: genai.Client, _message: str = message) -> types.GenerateContentResponse:
            return _call_gemini(c, system_prompt, _message)

        try:
            response = call_with_key_rotation(_make_call, client_override=client)
        except errors.APIError as exc:
            # 503s already retried (backoff, same key) inside _call_gemini;
            # 429s already retried (rotate key) inside call_with_key_rotation,
            # across every configured key. Either way this is not a "the
            # model produced bad JSON" failure the self-correction retry
            # below is for — it's the call itself never succeeding, so
            # there's nothing to self-correct against.
            raise ExtractionFailedError(
                f"Gemini API error during resume extraction: {exc}"
            ) from exc
        raw_text = response.text

        log_llm_call(
            stage="extraction",
            model=settings.gemini_extraction_model,
            request_payload={"user_message": user_message},
            response_payload={"raw_text": raw_text},
            attempt=attempt,
        )

        if raw_text is None:
            finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
            last_error = ValueError(f"Gemini returned no text (finish_reason={finish_reason})")
            logger.warning("Extraction attempt %d: %s", attempt, last_error)
            continue

        try:
            return ExtractedResume.model_validate_json(raw_text)
        except ValidationError as exc:
            last_error = exc
            logger.warning("Extraction attempt %d failed validation: %s", attempt, exc)

    raise ExtractionFailedError(
        f"Resume extraction failed validation after {settings.gemini_max_retries + 1} attempts: {last_error}"
    )
