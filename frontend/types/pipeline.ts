export interface InterviewQuestion {
  question: string
  category: string
  rationale: string | null
}

export interface CandidateReport {
  summary: string
  strengths: string[]
  concerns: string[]
  recommendation: string
}

export interface HiringState {
  candidate_id: string
  job_id: string
  resume_data: Record<string, unknown>
  jd_data: Record<string, unknown>
  match_score: number
  interview_questions: InterviewQuestion[]
  report: Partial<CandidateReport>
  current_step: string
  errors: string[]
}

export interface PipelineEvent {
  step: string
  state: HiringState
}

export type StepStatus = "pending" | "running" | "done" | "error"
