export type CandidateStatus = "new" | "screening" | "interviewing" | "offered" | "hired" | "rejected"

export interface CandidateListItem {
  id: string
  full_name: string | null
  email: string | null
  status: CandidateStatus
  skills: string[]
  applied_job_title: string | null
  applied_job_id: string | null
  match_score: number | null
  created_at: string
}

export interface CandidateListResponse {
  candidates: CandidateListItem[]
  total: number
}

export interface CandidateListFilters {
  status?: CandidateStatus
  skill?: string
  min_score?: number
  max_score?: number
}

export interface CandidateDeleteResponse {
  candidate_id: string
  interviews_deleted: number
  reports_deleted: number
  s3_objects_deleted: number
}
