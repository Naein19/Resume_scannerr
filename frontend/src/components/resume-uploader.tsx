"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ApiError,
  uploadResumes,
  uploadResumesFromGoogleSheetUrl,
  uploadResumesFromSheetFile,
} from "@/lib/api";
import type { BulkIngestRow, ResumeRead } from "@/lib/types";

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin text-primary"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

export function ResumeUploader({
  resumes,
  onUploaded,
}: {
  resumes: ResumeRead[];
  onUploaded: (resumes: ResumeRead[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const sheetFileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [stagedNames, setStagedNames] = useState<string[]>([]);
  const [failedLinks, setFailedLinks] = useState<BulkIngestRow[]>([]);

  const [sheetPanelOpen, setSheetPanelOpen] = useState(false);
  const [sheetUrl, setSheetUrl] = useState("");
  const [sheetBusy, setSheetBusy] = useState(false);

  function applyBulkResult(rows: BulkIngestRow[]) {
    const succeeded = rows.filter((r) => r.status === "success" && r.resume);
    const failed = rows.filter((r) => r.status === "failed");
    const newResumes = succeeded.map((r) => r.resume!);
    setFailedLinks((prev) => [...prev, ...failed]);
    if (newResumes.length > 0) onUploaded(newResumes);
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setStagedNames(Array.from(files).map((f) => f.name));
    setUploading(true);
    setError(null);
    try {
      const newResumes = await uploadResumes(Array.from(files));
      onUploaded(newResumes);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Upload failed — couldn't reach the backend.",
      );
    } finally {
      setUploading(false);
      setStagedNames([]);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleSheetFile(files: FileList | null) {
    if (!files || files.length === 0) return;
    setSheetBusy(true);
    setError(null);
    try {
      const result = await uploadResumesFromSheetFile(files[0]);
      applyBulkResult(result.results);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't read that sheet.");
    } finally {
      setSheetBusy(false);
      if (sheetFileInputRef.current) sheetFileInputRef.current.value = "";
    }
  }

  async function handleSheetUrl() {
    if (!sheetUrl.trim()) return;
    setSheetBusy(true);
    setError(null);
    try {
      const result = await uploadResumesFromGoogleSheetUrl(sheetUrl.trim());
      applyBulkResult(result.results);
      setSheetUrl("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't read that sheet.");
    } finally {
      setSheetBusy(false);
    }
  }

  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          void handleFiles(e.dataTransfer.files);
        }}
        className={`flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
          dragOver ? "border-primary bg-primary/5" : "border-border hover:border-muted-foreground"
        }`}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <Spinner />
            <div className="space-y-0.5">
              {stagedNames.map((name) => (
                <p key={name} className="font-mono text-xs text-muted-foreground">
                  {name}
                </p>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Extracting...</p>
          </div>
        ) : (
          <>
            <p className="text-sm font-medium text-foreground">
              Drop resumes here, or click to browse
            </p>
            <p className="text-xs text-muted-foreground">
              PDF or plain text, up to 5 MB each — select multiple to upload a batch
            </p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.txt,application/pdf,text/plain"
          className="hidden"
          onChange={(e) => void handleFiles(e.target.files)}
        />
      </label>

      {(resumes.length > 0 || failedLinks.length > 0) && (
        <ul className="mt-3 space-y-1">
          {resumes.map((resume) => (
            <li
              key={resume.id}
              className="flex items-center gap-2 font-mono text-xs text-muted-foreground"
            >
              <span
                className={
                  resume.extraction_status === "success"
                    ? "size-1.5 rounded-full bg-match"
                    : resume.extraction_status === "failed"
                      ? "size-1.5 rounded-full bg-destructive"
                      : "size-1.5 rounded-full bg-gap"
                }
                aria-hidden="true"
              />
              <span className="truncate">{resume.original_filename}</span>
            </li>
          ))}
          {failedLinks.map((row) => (
            <li
              key={row.source}
              className="flex items-start gap-2 font-mono text-xs text-muted-foreground"
              title={row.error ?? undefined}
            >
              <span className="mt-0.5 size-1.5 shrink-0 rounded-full bg-destructive" aria-hidden="true" />
              <span className="truncate">{row.source}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setSheetPanelOpen((v) => !v)}
          className="text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {sheetPanelOpen ? "Hide bulk import" : "Bulk import from a sheet of Drive links"}
        </button>
        <Button type="button" variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
          Choose files
        </Button>
      </div>

      {sheetPanelOpen && (
        <div className="mt-3 space-y-3 rounded-lg border border-border p-3">
          <div>
            <p className="text-xs font-medium text-foreground">CSV or XLSX file</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Any file with Google Drive resume links in its cells — column layout doesn&apos;t
              matter.
            </p>
            <input
              ref={sheetFileInputRef}
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="mt-2 text-xs text-muted-foreground file:mr-2 file:rounded-md file:border file:border-border file:bg-secondary file:px-2 file:py-1 file:text-xs file:text-foreground"
              onChange={(e) => void handleSheetFile(e.target.files)}
              disabled={sheetBusy}
            />
          </div>
          <div>
            <p className="text-xs font-medium text-foreground">Or a public Google Sheets URL</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Shared as &quot;Anyone with the link can view&quot; — private sheets can&apos;t be
              read.
            </p>
            <div className="mt-2 flex gap-2">
              <Input
                value={sheetUrl}
                onChange={(e) => setSheetUrl(e.target.value)}
                placeholder="https://docs.google.com/spreadsheets/d/..."
                disabled={sheetBusy}
                className="text-xs"
              />
              <Button type="button" size="sm" onClick={() => void handleSheetUrl()} disabled={sheetBusy}>
                {sheetBusy ? <Spinner /> : "Import"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </div>
  );
}
