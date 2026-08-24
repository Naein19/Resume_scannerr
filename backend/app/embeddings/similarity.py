"""Stage 2: a local, zero-API-cost cosine-similarity pre-filter that skips
Stage 3's expensive LLM judge call for candidates that are obviously not a
fit.

Trade-off, worth stating explicitly (see also README "threshold tuning"):
this is a recall/cost trade-off, not a free win. A low threshold lets more
borderline candidates through to the accurate-but-expensive LLM judge (few
false negatives, higher cost); a high threshold saves more LLM calls but
risks rejecting a candidate the LLM judge would have scored well, purely
because their resume's wording doesn't lexically/semantically resemble the
JD's wording. all-MiniLM-L6-v2 is a small, fast, general-purpose sentence
embedding model — good enough to separate "clearly unrelated" from
"plausibly relevant" cheaply, not precise enough to be the final judge.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.settings import settings
from app.schemas.extraction import ExtractedResume


@lru_cache
def _get_model() -> SentenceTransformer:
    # Loaded once per process (model load is ~seconds) and cached; every
    # subsequent call reuses the in-memory model.
    return SentenceTransformer(settings.embedding_model_name)


def candidate_profile_to_text(profile: ExtractedResume) -> str:
    """Flattens the structured profile into text for embedding. Uses the
    structured fields (skills, role/project names, technologies) rather
    than raw resume text so formatting artifacts (headers, page-2
    repetition, PDF extraction noise) don't dilute the semantic signal.

    Deliberately omits `description`/`role.description` free text, even
    though it's real signal — verified empirically, not just by
    intuition: for a resume with several substantial projects, including
    their full prose descriptions *dropped* cosine similarity against a
    matching JD from 0.53 to 0.28 (crossing the default 0.35 threshold
    into a false negative) versus the concise name+technologies version.
    A small averaging-based embedding model dilutes toward whatever text
    is longest; several paragraphs of implementation detail outweigh a
    short, keyword-dense skills list even when the skills list is the
    stronger relevance signal. The full description still reaches Stage
    3 — it's part of the structured JSON the LLM judge reads — this only
    affects what the cheap local pre-filter sees.
    """
    parts: list[str] = []
    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills))
    for role in profile.work_history:
        role_bits = [b for b in (role.title, role.company) if b]
        if role_bits:
            parts.append(" — ".join(role_bits))
    for project in profile.projects:
        # Projects are the dominant experience section on student/
        # early-career resumes with no work_history — omitting them here
        # would mean the pre-filter judges those candidates on their skills
        # list alone, which is a weaker signal than what they built.
        technologies = ", ".join(project.technologies) if project.technologies else None
        project_bits = [b for b in (project.name, technologies) if b]
        if project_bits:
            parts.append(" — ".join(project_bits))
    for edu in profile.education:
        edu_bits = [b for b in (edu.degree, edu.institution) if b]
        if edu_bits:
            parts.append(" — ".join(edu_bits))
    if profile.certifications:
        parts.append("Certifications: " + ", ".join(profile.certifications))
    return "\n".join(parts)


def cosine_similarity(text_a: str, text_b: str) -> float:
    model = _get_model()
    embeddings = model.encode([text_a, text_b], normalize_embeddings=True)
    return float(np.dot(embeddings[0], embeddings[1]))


def passes_prefilter(similarity: float, threshold: float | None = None) -> bool:
    threshold = settings.embedding_similarity_threshold if threshold is None else threshold
    return similarity >= threshold
