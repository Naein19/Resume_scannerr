"""Round-robins across every configured Gemini API key.

Each of GOOGLE_API_KEY, GOOGLE_API_KEY1, GOOGLE_API_KEY2, GOOGLE_API_KEY3
is its own independent free-tier quota. Rotating to the next key on a 429
(quota exhausted) is the free-tier equivalent of paying for more headroom
— it doesn't fix a genuinely overloaded model (that's the 503 backoff
retry in `gemini_retry.py`), it fixes "this specific key's daily/per-minute
allowance ran out, but a sibling key hasn't touched its own yet."
"""

import logging
from collections.abc import Callable
from typing import TypeVar

from google import genai
from google.genai import errors

from app.core.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GeminiKeyPool:
    def __init__(self, api_keys: list[str]) -> None:
        if not api_keys:
            raise ValueError("At least one Gemini API key is required")
        self._keys = api_keys
        self._index = 0
        self._clients: dict[int, genai.Client] = {}

    @property
    def size(self) -> int:
        return len(self._keys)

    def current_client(self) -> genai.Client:
        if self._index not in self._clients:
            self._clients[self._index] = genai.Client(api_key=self._keys[self._index])
        return self._clients[self._index]

    def rotate(self) -> genai.Client:
        previous, self._index = self._index, (self._index + 1) % len(self._keys)
        logger.warning(
            "Gemini key %d hit a quota/rate limit; rotating to key %d of %d",
            previous,
            self._index,
            self.size,
        )
        return self.current_client()


_pool: GeminiKeyPool | None = None


def get_pool() -> GeminiKeyPool:
    global _pool
    if _pool is None:
        _pool = GeminiKeyPool(settings.google_api_keys)
    return _pool


def call_with_key_rotation(
    make_call: Callable[[genai.Client], T], *, client_override: genai.Client | None = None
) -> T:
    """Runs `make_call(client)`, rotating to the next configured API key
    and retrying on a 429 (quota exhausted) until every key has been
    tried. `client_override` bypasses the pool entirely — used by tests
    that inject a mock client, where rotation would just mean retrying
    against the same mock.
    """
    if client_override is not None:
        return make_call(client_override)

    pool = get_pool()
    attempts_left = pool.size
    last_exc: errors.ClientError | None = None
    while attempts_left > 0:
        client = pool.current_client()
        try:
            return make_call(client)
        except errors.ClientError as exc:
            if getattr(exc, "code", None) != 429:
                raise
            last_exc = exc
            attempts_left -= 1
            if attempts_left > 0:
                pool.rotate()

    assert last_exc is not None  # loop only exits early via return or raise
    raise last_exc
