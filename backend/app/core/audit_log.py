"""Structured, PII-redacted logging for every LLM call.

Extraction and scoring both call `log_llm_call` on every request/response so
a wrong score or a bad extraction can be traced back to the exact prompt
that produced it — a real production requirement, not decoration. PII
(name/email/phone) is stripped before anything hits the log stream, since
logs typically have weaker access controls and longer retention than the
primary database.
"""

import copy
import json
import logging
from typing import Any

logger = logging.getLogger("llm_audit")

_PII_KEYS = {"name", "email", "phone"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k in _PII_KEYS and v else _redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log_llm_call(
    *,
    stage: str,
    model: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    attempt: int = 1,
) -> None:
    redacted_request = _redact(copy.deepcopy(request_payload))
    redacted_response = _redact(copy.deepcopy(response_payload))
    logger.info(
        json.dumps(
            {
                "stage": stage,
                "model": model,
                "attempt": attempt,
                "request": redacted_request,
                "response": redacted_response,
            },
            default=str,
        )
    )
