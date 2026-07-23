export type CandidateStatus =
  | "new"
  | "screening"
  | "interviewing"
  | "offered"
  | "hired"
  | "rejected";

export interface Candidate {
  id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  resume_url?: string | null;
  skills?: string[] | null;
  experience_years?: number | null;
  status: CandidateStatus;
  created_at: string;
  updated_at: string;
}

export type JobStatus = "draft" | "open" | "paused" | "closed";
export type EmploymentType = "full_time" | "part_time" | "contract" | "internship";

export interface Job {
  id: string;
  title: string;
  description: string;
  department?: string | null;
  location?: string | null;
  employment_type: EmploymentType;
  min_experience?: number | null;
  max_experience?: number | null;
  required_skills?: string[] | null;
  status: JobStatus;
  created_at: string;
  updated_at: string;
}

export type InterviewType = "screening" | "technical" | "behavioral" | "final";
export type InterviewStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "no_show";

export interface Interview {
  id: string;
  candidate_id: string;
  job_id: string;
  interview_type: InterviewType;
  status: InterviewStatus;
  scheduled_at?: string | null;
  duration_minutes?: number | null;
  ai_score?: number | null;
  created_at: string;
  updated_at: string;
}
