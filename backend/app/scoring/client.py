"""Stage 3: structured candidate profile + JD -> validated `ScoringResult`,
via the same structured-output + self-correction-retry pattern as Stage 1
(app/extraction/client.py). Kept as a separate call site (not a shared
"call_gemini_with_schema" abstraction shared across both stages) because
the two stages log under different `stage` labels and retry with different
prompt builders — the duplication is two small functions, not worth an
abstraction that would make one stage's prompt debugging touch the other.
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
from app.schemas.scoring import ScoringResult
from prompts import scoring_v1

logger = logging.getLogger(__name__)

_RESPONSE_SCHEMA = ScoringResult.model_json_schema()


class ScoringFailedError(Exception):
    pass


@retry_transient_gemini_errors
def _call_gemini(client: genai.Client, user_message: str) -> types.GenerateContentResponse:
    return client.models.generate_content(
        model=settings.gemini_scoring_model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=scoring_v1.SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=_RESPONSE_SCHEMA,
        ),
    )


def score_candidate(
    candidate_profile: ExtractedResume,
    job_description_text: str,
    client: genai.Client | None = None,
) -> ScoringResult:
    candidate_json = candidate_profile.model_dump_json()
    user_message = scoring_v1.build_user_message(candidate_json, job_description_text)

    last_error: Exception | None = None
    for attempt in range(1, settings.gemini_max_retries + 2):
        message = (
            user_message
            if attempt == 1
            else scoring_v1.build_retry_message(
                candidate_json, job_description_text, str(last_error)
            )
        )
        def _make_call(c: genai.Client, _message: str = message) -> types.GenerateContentResponse:
            return _call_gemini(c, _message)

        try:
            response = call_with_key_rotation(_make_call, client_override=client)
        except errors.APIError as exc:
            raise ScoringFailedError(f"Gemini API error during scoring: {exc}") from exc
        raw_text = response.text

        log_llm_call(
            stage="scoring",
            model=settings.gemini_scoring_model,
            request_payload={"user_message": user_message},
            response_payload={"raw_text": raw_text},
            attempt=attempt,
        )

        if raw_text is None:
            finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
            last_error = ValueError(f"Gemini returned no text (finish_reason={finish_reason})")
            logger.warning("Scoring attempt %d: %s", attempt, last_error)
            continue

        try:
            return ScoringResult.model_validate_json(raw_text)
        except ValidationError as exc:
            last_error = exc
            logger.warning("Scoring attempt %d failed validation: %s", attempt, exc)

    raise ScoringFailedError(
        f"Candidate scoring failed validation after {settings.gemini_max_retries + 1} attempts: {last_error}"
    )
