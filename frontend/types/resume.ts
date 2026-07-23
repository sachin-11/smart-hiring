export type ParsingStatus = "pending" | "processing" | "completed" | "failed"

export interface ExperienceEntry {
  company: string
  title: string
  start_date: string | null
  end_date: string | null
  is_current: boolean
  description: string | null
}

export interface EducationEntry {
  institution: string
  degree: string | null
  field_of_study: string | null
  start_year: number | null
  end_year: number | null
}

export interface ResumeUploadResponse {
  candidate_id: string
  status: ParsingStatus
}

export interface ResumeStatusResponse {
  candidate_id: string
  status: ParsingStatus
  error: string | null
}

export interface ResumeDetailResponse {
  id: string
  status: ParsingStatus
  error: string | null
  original_filename: string | null
  full_name: string | null
  email: string | null
  phone: string | null
  skills: string[] | null
  experience: ExperienceEntry[] | null
  education: EducationEntry[] | null
  total_years_exp: number | null
  resume_url: string | null
}
