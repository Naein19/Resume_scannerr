export type ExtractionStatus = "pending" | "success" | "failed";

export interface WorkHistoryEntry {
  company: string | null;
  title: string | null;
  start: string | null;
  end: string | null;
  description: string | null;
}

export interface EducationEntry {
  degree: string | null;
  institution: string | null;
  year: string | null;
}

export interface ProjectEntry {
  name: string | null;
  technologies: string[];
  description: string | null;
}

export interface ExtractedResume {
  name: string | null;
  email: string | null;
  phone: string | null;
  skills: string[];
  total_experience_years: number | null;
  work_history: WorkHistoryEntry[];
  projects: ProjectEntry[];
  education: EducationEntry[];
  certifications: string[];
}

export interface ResumeRead {
  id: string;
  candidate_id: string | null;
  original_filename: string;
  extraction_status: ExtractionStatus;
  extraction_error: string | null;
  extracted_data: ExtractedResume | null;
}

export interface JobDescriptionRead {
  id: string;
  title: string;
  raw_text: string;
  created_at: string;
}

export type MatchStage = "prefiltered_out" | "scored";

export interface ShortlistEntry {
  match_result_id: string;
  candidate_id: string;
  candidate_name: string | null;
  candidate_email: string | null;
  resume_id: string | null;
  stage: MatchStage;
  embedding_similarity: number | null;
  score: number | null;
  justification: string | null;
  matched_skills: string[] | null;
  missing_skills: string[] | null;
}

export interface ShortlistResponse {
  job_description_id: string;
  total_candidates: number;
  prefiltered_out: number;
  scored: number;
  results: ShortlistEntry[];
}

export interface BulkIngestRow {
  source: string;
  status: "success" | "failed";
  resume: ResumeRead | null;
  error: string | null;
}

export interface BulkIngestResponse {
  total_links_found: number;
  results: BulkIngestRow[];
}
