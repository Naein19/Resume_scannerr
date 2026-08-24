"""Threshold logic for the Stage 2 pre-filter. Deliberately does not load
the real sentence-transformers model — that's exercised in
test_matching_service.py, where a real similarity score needs to separate
a relevant from an irrelevant candidate. This file is the fast, model-free
test of the actual decision logic: given a similarity score, does the
candidate pass or get filtered out.
"""

from app.embeddings.similarity import candidate_profile_to_text, passes_prefilter
from app.schemas.extraction import ExtractedResume, ProjectEntry, WorkHistoryEntry


def test_passes_at_exactly_the_threshold():
    assert passes_prefilter(0.35, threshold=0.35) is True


def test_fails_just_below_threshold():
    assert passes_prefilter(0.349, threshold=0.35) is False


def test_passes_well_above_threshold():
    assert passes_prefilter(0.8, threshold=0.35) is True


def test_uses_settings_default_when_threshold_omitted():
    # settings.embedding_similarity_threshold defaults to 0.35
    assert passes_prefilter(0.9) is True
    assert passes_prefilter(-1.0) is False


def test_profile_to_text_includes_skills_and_roles():
    profile = ExtractedResume(
        skills=["Python", "SQL"],
        work_history=[
            WorkHistoryEntry(
                title="Backend Engineer", company="Acme", description="Built APIs"
            )
        ],
    )
    text = candidate_profile_to_text(profile)
    assert "Python" in text
    assert "Backend Engineer" in text
    assert "Acme" in text


def test_profile_to_text_handles_empty_profile():
    assert candidate_profile_to_text(ExtractedResume()) == ""


def test_profile_to_text_includes_projects_for_no_work_history_resumes():
    # The exact shape of a student resume: no work_history, real signal
    # lives in projects. If this text omitted projects, the embedding
    # pre-filter would judge such a candidate on their skills list alone.
    profile = ExtractedResume(
        skills=["Python"],
        projects=[
            ProjectEntry(
                name="TaskFlow",
                technologies=["Next.js", "Supabase"],
                description="Real-time task board",
            )
        ],
    )
    text = candidate_profile_to_text(profile)
    assert "TaskFlow" in text
    assert "Next.js" in text


def test_profile_to_text_omits_free_text_descriptions():
    # Verified empirically (see candidate_profile_to_text's docstring):
    # including full description prose measurably dilutes the embedding
    # signal versus the concise title/name + technologies version. This
    # locks in that the omission is deliberate, not an accidental drop.
    profile = ExtractedResume(
        work_history=[
            WorkHistoryEntry(
                title="Backend Engineer",
                company="Acme",
                description="A long paragraph of implementation detail that should not appear",
            )
        ],
        projects=[
            ProjectEntry(
                name="TaskFlow",
                technologies=["Next.js"],
                description="Another long paragraph that should not appear",
            )
        ],
    )
    text = candidate_profile_to_text(profile)
    assert "implementation detail" not in text
    assert "long paragraph" not in text
