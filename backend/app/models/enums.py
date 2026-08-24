"""The only two controlled vocabularies in the data model. Plain string
enums — not tied to any ORM — since MongoDB documents are just dicts;
these exist so the rest of the codebase references `ExtractionStatus.SUCCESS`
instead of the string literal `"success"` scattered everywhere.
"""

import enum


class ExtractionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class MatchStage(str, enum.Enum):
    """Which stage produced the final verdict, for audit/debugging.

    PREFILTERED_OUT means Stage 2 (embeddings) rejected the candidate
    before any LLM scoring call was made — score/justification are null and
    no LLM cost was incurred. SCORED means the candidate passed the
    pre-filter and Stage 3 (the LLM judge) produced a real score.
    """

    PREFILTERED_OUT = "prefiltered_out"
    SCORED = "scored"
