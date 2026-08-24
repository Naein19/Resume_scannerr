"use client";

import { useMemo, useState } from "react";
import { CandidateCard } from "@/components/candidate-card";
import { JobForm } from "@/components/job-form";
import { ResumeUploader } from "@/components/resume-uploader";
import { Button } from "@/components/ui/button";
import { ApiError, runMatch } from "@/lib/api";
import type { JobDescriptionRead, ResumeRead, ShortlistResponse } from "@/lib/types";

function StepNumber({ n, done }: { n: number; done: boolean }) {
  return (
    <span
      className={`font-display text-lg tabular-nums ${done ? "text-primary" : "text-muted-foreground"}`}
    >
      {String(n).padStart(2, "0")}
    </span>
  );
}

function EmptyShortlistIcon() {
  return (
    <svg
      className="size-8 text-muted-foreground"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4" y="3" width="12" height="16" rx="1.5" />
      <path d="M7 8h6M7 11.5h6M7 15h3.5" />
      <circle cx="17" cy="17" r="4" />
      <path d="M19.8 19.8 22.5 22.5" />
    </svg>
  );
}

export default function Home() {
  const [job, setJob] = useState<JobDescriptionRead | null>(null);
  const [resumes, setResumes] = useState<ResumeRead[]>([]);
  const [shortlist, setShortlist] = useState<ShortlistResponse | null>(null);
  const [matching, setMatching] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0);
  const [showFiltered, setShowFiltered] = useState(true);

  const visibleResults = useMemo(() => {
    if (!shortlist) return [];
    return shortlist.results.filter((r) => {
      if (r.stage === "prefiltered_out") return showFiltered;
      return (r.score ?? 0) >= threshold;
    });
  }, [shortlist, threshold, showFiltered]);

  async function handleRunMatch() {
    if (!job) return;
    // Scope matching to exactly the candidates uploaded in this session —
    // omitting candidate_ids would match every resume ever ingested by
    // anyone against this backend, including candidates from unrelated
    // sessions. The shortlist should only ever show what you put in.
    const candidateIds = resumes
      .map((r) => r.candidate_id)
      .filter((id): id is string => id !== null);
    if (candidateIds.length === 0) return;

    setMatching(true);
    setMatchError(null);
    try {
      const result = await runMatch(job.id, candidateIds);
      setShortlist(result);
    } catch (err) {
      setMatchError(err instanceof ApiError ? err.message : "Couldn't reach the backend.");
    } finally {
      setMatching(false);
    }
  }

  function handleCandidateDeleted(candidateId: string) {
    setResumes((prev) => prev.filter((r) => r.candidate_id !== candidateId));
    setShortlist((prev) => {
      if (!prev) return prev;
      const results = prev.results.filter((r) => r.candidate_id !== candidateId);
      return {
        ...prev,
        results,
        total_candidates: results.length,
        scored: results.filter((r) => r.stage === "scored").length,
        prefiltered_out: results.filter((r) => r.stage === "prefiltered_out").length,
      };
    });
  }

  const successfulResumes = resumes.filter((r) => r.extraction_status === "success");
  const failedResumes = resumes.filter((r) => r.extraction_status === "failed");

  return (
    <div className="mx-auto w-full max-w-6xl flex-1 px-6 py-10 md:px-10">
      <header className="mb-10 border-b border-border pb-6">
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Smart Resume Screener
        </p>
        <h1 className="mt-1 font-display text-3xl text-foreground">
          Screen candidates against a role, with evidence.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Extraction, an embedding pre-filter, and an LLM judge scored against a rubric — every
          score comes with the skills that earned it and the ones that didn&apos;t.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[380px_1fr]">
        <div className="space-y-6">
          <section className="rounded-lg border border-border bg-card p-5">
            <h2 className="flex items-baseline gap-2.5 font-display text-lg text-foreground">
              <StepNumber n={1} done={job !== null} />
              Job description
            </h2>
            {job ? (
              <div className="mt-3">
                <p className="font-medium text-foreground">{job.title}</p>
                <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{job.raw_text}</p>
                <Button variant="ghost" size="sm" className="mt-2 -ml-2.5" onClick={() => setJob(null)}>
                  Change
                </Button>
              </div>
            ) : (
              <div className="mt-3">
                <JobForm onCreated={setJob} />
              </div>
            )}
          </section>

          <section className="rounded-lg border border-border bg-card p-5">
            <h2 className="flex items-baseline gap-2.5 font-display text-lg text-foreground">
              <StepNumber n={2} done={successfulResumes.length > 0} />
              Resumes
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {resumes.length === 0
                ? "Upload one or more candidate resumes."
                : `${successfulResumes.length} ready${
                    failedResumes.length > 0 ? `, ${failedResumes.length} failed` : ""
                  }.`}
            </p>
            <div className="mt-3">
              <ResumeUploader
                resumes={resumes}
                onUploaded={(r) => setResumes((prev) => [...prev, ...r])}
              />
            </div>
            {failedResumes.length > 0 && (
              <ul className="mt-3 space-y-1">
                {failedResumes.map((r) => (
                  <li key={r.id} className="text-xs text-destructive">
                    {r.original_filename}: {r.extraction_error}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-border bg-card p-5">
            <h2 className="flex items-baseline gap-2.5 font-display text-lg text-foreground">
              <StepNumber n={3} done={shortlist !== null} />
              Match
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Runs the embedding pre-filter, then the LLM judge for every candidate that passes
              it.
            </p>
            <Button
              className="mt-3 w-full"
              disabled={!job || successfulResumes.length === 0 || matching}
              onClick={handleRunMatch}
            >
              {matching ? "Matching..." : "Run matching"}
            </Button>
            {matchError && <p className="mt-2 text-sm text-destructive">{matchError}</p>}
          </section>
        </div>

        <div>
          {shortlist ? (
            <>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-4">
                <div>
                  <h2 className="font-display text-xl text-foreground">Shortlist</h2>
                  <p className="text-sm text-muted-foreground">
                    {shortlist.scored} scored &middot; {shortlist.prefiltered_out} filtered out of{" "}
                    {shortlist.total_candidates} candidates
                  </p>
                </div>
                <div className="flex items-end gap-4">
                  <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                    Min score: <span className="font-mono tabular-nums text-foreground">{threshold}</span>
                    <input
                      type="range"
                      min={0}
                      max={10}
                      value={threshold}
                      onChange={(e) => setThreshold(Number(e.target.value))}
                      className="w-32 accent-primary"
                    />
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={showFiltered}
                      onChange={(e) => setShowFiltered(e.target.checked)}
                      className="accent-primary"
                    />
                    Show filtered out
                  </label>
                </div>
              </div>

              {visibleResults.length === 0 ? (
                <p className="text-sm text-muted-foreground">No candidates match this threshold.</p>
              ) : (
                <ul className="space-y-3">
                  {visibleResults.map((entry, i) => (
                    <CandidateCard
                      key={entry.match_result_id}
                      entry={entry}
                      rank={i + 1}
                      onDeleted={handleCandidateDeleted}
                    />
                  ))}
                </ul>
              )}
            </>
          ) : (
            <div className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border text-center">
              <EmptyShortlistIcon />
              <p className="max-w-xs text-sm text-muted-foreground">
                Add a job description and resumes, then run matching to see the shortlist here.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
