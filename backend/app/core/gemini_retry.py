"""Retry policy for a transient Gemini 503 (model temporarily overloaded).

Deliberately separate from two other things it could be confused with:
the self-correction retry in the extraction/scoring clients (that one
retries with a *different* prompt because the model's *output* was
wrong — this retries the *same* request because the call itself failed),
and 429 quota errors (handled by rotating to a different API key in
`gemini_pool.py`/the extraction & scoring clients, not by backing off on
the same exhausted key). Discovered live: a real `/resumes` upload hit a
genuine 503 from `gemini-2.5-flash` under load and crashed the whole
request with an unhandled 500 instead of failing one resume gracefully.
"""

from google.genai import errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_server_overloaded(exc: BaseException) -> bool:
    return isinstance(exc, errors.ServerError)


retry_transient_gemini_errors = retry(
    retry=retry_if_exception(_is_server_overloaded),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
