import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import candidates, jobs, resumes
from app.core.rate_limit import limiter
from app.core.settings import settings
from app.db.mongo import ensure_indexes, get_database

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # No migration tool for a schema-less store — indexes are the closest
    # thing to a schema here, so they're ensured once at startup instead.
    ensure_indexes(get_database())
    yield


app = FastAPI(
    title="Smart Resume Screener",
    description=(
        "Two-stage LLM resume screening: structured extraction (Stage 1) "
        "feeds an embedding pre-filter (Stage 2) and an LLM judge (Stage 3) "
        "that produces a ranked, justified shortlist against a job "
        "description."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
# slowapi's handler predates this Starlette version's more specific
# generic Request[State] signature on add_exception_handler; the runtime
# behavior is correct, only the type stub is stale.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.environment == "development" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(resumes.router)
app.include_router(candidates.router)


@app.get("/health", summary="Liveness check")
async def health() -> dict[str, str]:
    return {"status": "ok"}
