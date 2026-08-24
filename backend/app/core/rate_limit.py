"""Per-IP rate limiting via slowapi (a Flask-Limiter port for ASGI).
Applied because every write endpoint here triggers an LLM call against
Gemini's free-tier quota — without a limit, one client can exhaust that
quota for everyone. The same limiter would matter even more on a paid
provider, where the exposure is real spend instead of a shared rate cap.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.settings import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])
