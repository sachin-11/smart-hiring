export type Recommendation = "Strongly Hire" | "Hire" | "Hold" | "Reject"
export type ProficiencyLevel = "Beginner" | "Intermediate" | "Advanced" | "Expert"

export interface TechnicalAssessment {
  score: number
  strengths: string[]
  gaps: string[]
  comments: string
}

export interface CommunicationAssessment {
  score: number
  clarity: string
  articulation: string
  examples: string[]
}

export interface CultureFit {
  score: number
  comments: string
}

export interface SkillBreakdownItem {
  skill: string
  proficiency_level: ProficiencyLevel
  evidence: string
}

export interface InterviewHighlights {
  best_answer: string
  concern_answer: string
}

export interface ReportSchema {
  overall_score: number
  recommendation: Recommendation
  technical_assessment: TechnicalAssessment
  communication_assessment: CommunicationAssessment
  culture_fit: CultureFit
  skill_breakdown: SkillBreakdownItem[]
  interview_highlights: InterviewHighlights
  suggested_next_steps: string
  red_flags: string[]
}

export interface ReportDetailResponse {
  report_id: string
  interview_id: string
  candidate_id: string
  job_id: string
  candidate_name: string | null
  job_title: string | null
  created_at: string
  report: ReportSchema
}

export interface ReportPdfResponse {
  report_id: string
  pdf_url: string
}

export interface ReportShareResponse {
  sent: boolean
  detail: string
}
