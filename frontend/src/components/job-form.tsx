"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createJob } from "@/lib/api";
import type { JobDescriptionRead } from "@/lib/types";

export function JobForm({ onCreated }: { onCreated: (job: JobDescriptionRead) => void }) {
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const job = await createJob(title.trim(), rawText.trim());
      onCreated(job);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the backend.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="job-title">Role title</Label>
        <Input
          id="job-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Senior Backend Engineer"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="job-text">Job description</Label>
        <Textarea
          id="job-text"
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="Paste the full job description — required skills, experience level, responsibilities..."
          className="min-h-40"
          required
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Saving..." : "Save job description"}
      </Button>
    </form>
  );
}
