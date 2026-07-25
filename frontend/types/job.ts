export type EmploymentType = "full_time" | "part_time" | "contract" | "internship"
export type JobStatus = "draft" | "open" | "paused" | "closed"
export type SeniorityLevel = "junior" | "mid" | "senior" | "lead" | "principal"

export interface JobCreateRequest {
  title: string
  description: string
  required_skills: string[]
  min_experience: number | null
  max_experience: number | null
}

export interface JobDetailResponse {
  id: string
  title: string
  description: string
  department: string | null
  location: string | null
  employment_type: EmploymentType
  min_experience: number | null
  max_experience: number | null
  required_skills: string[] | null
  nice_to_have_skills: string[] | null
  responsibilities: string[] | null
  seniority_level: SeniorityLevel | null
  status: JobStatus
  created_at: string
}

export interface JobListItem {
  id: string
  title: string
  department: string | null
  location: string | null
  status: JobStatus
  applicant_count: number
  top_match_score: number | null
  created_at: string
}

export interface JobListResponse {
  jobs: JobListItem[]
  total: number
}

export interface JobDeleteResponse {
  job_id: string
  applications_deleted: number
  interviews_deleted: number
  reports_deleted: number
  s3_objects_deleted: number
}
