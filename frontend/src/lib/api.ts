import type {
  BulkIngestResponse,
  JobDescriptionRead,
  ResumeRead,
  ShortlistResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export function createJob(title: string, rawText: string): Promise<JobDescriptionRead> {
  return request<JobDescriptionRead>("/jobs", {
    method: "POST",
    body: JSON.stringify({ title, raw_text: rawText }),
  });
}

export function uploadResumes(files: File[]): Promise<ResumeRead[]> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  return request<ResumeRead[]>("/resumes", { method: "POST", body: formData });
}

export function uploadResumesFromSheetFile(file: File): Promise<BulkIngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<BulkIngestResponse>("/resumes/from-sheet", { method: "POST", body: formData });
}

export function uploadResumesFromGoogleSheetUrl(sheetUrl: string): Promise<BulkIngestResponse> {
  const formData = new FormData();
  formData.append("google_sheet_url", sheetUrl);
  return request<BulkIngestResponse>("/resumes/from-sheet", { method: "POST", body: formData });
}

export function runMatch(jobId: string, candidateIds: string[]): Promise<ShortlistResponse> {
  return request<ShortlistResponse>(`/jobs/${jobId}/match`, {
    method: "POST",
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
}

export function getResumeFileUrl(resumeId: string): string {
  return `${API_URL}/resumes/${resumeId}/file`;
}

export function getShortlist(jobId: string): Promise<ShortlistResponse> {
  return request<ShortlistResponse>(`/jobs/${jobId}/shortlist`);
}

export function deleteCandidate(candidateId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/candidates/${candidateId}`, { method: "DELETE" });
}

export { ApiError };
