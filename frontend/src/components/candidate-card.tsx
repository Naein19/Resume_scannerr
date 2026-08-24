"use client";

import { useRef, useState } from "react";
import { ScoreBar } from "@/components/score-bar";
import { deleteCandidate, getResumeFileUrl } from "@/lib/api";
import type { ShortlistEntry } from "@/lib/types";

function DocumentIcon() {
  return (
    <svg
      className="size-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      className="size-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 6h16" />
      <path d="M6 6v14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

export function CandidateCard({
  entry,
  rank,
  onDeleted,
}: {
  entry: ShortlistEntry;
  rank: number;
  onDeleted: (candidateId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const revertTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefiltered = entry.stage === "prefiltered_out";

  function handleDeleteClick() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      revertTimer.current = setTimeout(() => setConfirmingDelete(false), 4000);
      return;
    }

    if (revertTimer.current) clearTimeout(revertTimer.current);
    setDeleting(true);
    setDeleteError(null);
    deleteCandidate(entry.candidate_id)
      .then(() => onDeleted(entry.candidate_id))
      .catch(() => {
        setDeleteError("Couldn't delete — try again.");
        setDeleting(false);
        setConfirmingDelete(false);
      });
  }

  return (
    <li className="rounded-lg border border-border bg-card">
      <div className="flex items-start gap-4 p-4">
        <span className="mt-1 font-display text-lg tabular-nums text-muted-foreground">
          {String(rank).padStart(2, "0")}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate font-display text-lg text-foreground">
                  {entry.candidate_name ?? "Unnamed candidate"}
                </p>
                {entry.resume_id && (
                  <a
                    href={getResumeFileUrl(entry.resume_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    title="Open the original resume file in a new tab"
                  >
                    <DocumentIcon />
                    View resume
                  </a>
                )}
              </div>
              <p className="truncate text-sm text-muted-foreground">{entry.candidate_email}</p>
            </div>

            <div className="flex items-center gap-3">
              <ScoreBar score={entry.score} />
              <button
                type="button"
                onClick={handleDeleteClick}
                disabled={deleting}
                aria-label={
                  confirmingDelete ? "Confirm permanent delete" : "Delete candidate permanently"
                }
                title={
                  confirmingDelete
                    ? "Click again to permanently delete — cannot be undone"
                    : "Permanently delete this candidate"
                }
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50 ${
                  confirmingDelete
                    ? "border-destructive bg-destructive/10 text-destructive"
                    : "border-border text-muted-foreground hover:border-destructive hover:text-destructive"
                }`}
              >
                <TrashIcon />
                {deleting ? "Deleting..." : confirmingDelete ? "Confirm?" : "Delete"}
              </button>
            </div>
          </div>

          {deleteError && <p className="mt-2 text-xs text-destructive">{deleteError}</p>}

          {prefiltered ? (
            <p className="mt-3 text-sm text-muted-foreground">
              Filtered out before scoring
              {entry.embedding_similarity !== null && (
                <>
                  {" "}
                  &mdash; embedding similarity{" "}
                  <span className="font-mono tabular-nums">
                    {entry.embedding_similarity.toFixed(2)}
                  </span>{" "}
                  was below the match threshold.
                </>
              )}
            </p>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {entry.matched_skills?.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full bg-match/15 px-2.5 py-0.5 text-xs font-medium text-match"
                  >
                    {skill}
                  </span>
                ))}
                {entry.missing_skills?.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full bg-gap/15 px-2.5 py-0.5 text-xs font-medium text-gap"
                  >
                    {skill} &middot; gap
                  </span>
                ))}
              </div>

              {entry.justification && (
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    aria-expanded={expanded}
                  >
                    {expanded ? "Hide justification" : "Show justification"}
                  </button>
                  {expanded && (
                    <p className="mt-2 text-sm leading-relaxed text-foreground/90">
                      {entry.justification}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </li>
  );
}
