"""Multi-key rotation: each of GOOGLE_API_KEY/1/2/3 is an independent
free-tier quota, so a 429 on one key should fail over to the next rather
than failing the request outright.
"""

from unittest.mock import MagicMock

import pytest
from google.genai import errors

from app.core.gemini_pool import GeminiKeyPool, call_with_key_rotation


def _quota_error() -> errors.ClientError:
    return errors.ClientError(
        429, {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, None
    )


def _other_client_error() -> errors.ClientError:
    return errors.ClientError(
        400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}}, None
    )


def test_pool_rotates_through_keys_in_order():
    pool = GeminiKeyPool(["key-a", "key-b", "key-c"])
    assert pool.current_client() is pool.current_client()  # same client reused for a given key

    pool.rotate()
    second_client = pool.current_client()
    pool.rotate()
    third_client = pool.current_client()
    pool.rotate()  # wraps back to the first key
    assert pool.current_client() is not second_client
    assert pool.current_client() is not third_client


def test_pool_requires_at_least_one_key():
    with pytest.raises(ValueError, match="At least one"):
        GeminiKeyPool([])


def test_call_with_key_rotation_falls_over_to_next_key_on_429():
    pool = GeminiKeyPool(["key-a", "key-b"])
    calls_by_key: list[int] = []

    def make_call(client: object) -> str:
        # Identify which key's client this is by object identity against the pool.
        calls_by_key.append(id(client))
        if len(calls_by_key) == 1:
            raise _quota_error()
        return "success"

    import app.core.gemini_pool as gemini_pool_module

    gemini_pool_module._pool = pool  # use our pool instance instead of the module singleton
    try:
        result = call_with_key_rotation(make_call)
    finally:
        gemini_pool_module._pool = None

    assert result == "success"
    assert len(calls_by_key) == 2
    assert calls_by_key[0] != calls_by_key[1]  # second attempt used a different key's client


def test_call_with_key_rotation_raises_after_exhausting_every_key():
    pool = GeminiKeyPool(["key-a", "key-b"])

    def always_quota_exhausted(client: object) -> str:
        raise _quota_error()

    import app.core.gemini_pool as gemini_pool_module

    gemini_pool_module._pool = pool
    try:
        with pytest.raises(errors.ClientError):
            call_with_key_rotation(always_quota_exhausted)
    finally:
        gemini_pool_module._pool = None


def test_call_with_key_rotation_does_not_retry_non_quota_client_errors():
    pool = GeminiKeyPool(["key-a", "key-b"])
    attempts = 0

    def bad_request(client: object) -> str:
        nonlocal attempts
        attempts += 1
        raise _other_client_error()

    import app.core.gemini_pool as gemini_pool_module

    gemini_pool_module._pool = pool
    try:
        with pytest.raises(errors.ClientError):
            call_with_key_rotation(bad_request)
    finally:
        gemini_pool_module._pool = None

    assert attempts == 1  # a 400 is not a quota error — must not rotate/retry


def test_client_override_bypasses_pool_entirely():
    mock_client = MagicMock()
    result = call_with_key_rotation(lambda c: "used override" if c is mock_client else "wrong", client_override=mock_client)
    assert result == "used override"
