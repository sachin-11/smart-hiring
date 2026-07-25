export type InterviewStatus = "scheduled" | "in_progress" | "completed" | "cancelled" | "no_show"
export type QuestionCategory = "technical" | "behavioral" | "situational" | "culture" | "intro"

export interface InterviewStartResponse {
  session_id: string
  question: string
  category: QuestionCategory
  question_index: number
  total_questions: number
  audio_url: string | null
  access_token: string
  access_url: string
}

export interface InterviewAnswerResponse {
  session_id: string
  score: number | null
  feedback: string | null
  is_follow_up: boolean
  complete: boolean
  question: string | null
  category: QuestionCategory | null
  question_index: number
  total_questions: number
  audio_url: string | null
}

export interface QAExchange {
  question: string
  category: QuestionCategory
  is_follow_up: boolean
  answer: string | null
  score: number | null
  feedback: string | null
}

export interface InterviewTranscriptResponse {
  session_id: string
  candidate_id: string
  job_id: string
  status: InterviewStatus
  exchanges: QAExchange[]
  question_index: number
  total_questions: number
  average_score: number | null
}

export interface InterviewStopResponse {
  session_id: string
  status: InterviewStatus
  questions_answered: number
}

export interface InterviewDeleteResponse {
  session_id: string
  s3_objects_deleted: number
}

/** Messages the /ws/interview/{sessionId} socket sends to the client. */
export type InterviewWsServerMessage =
  | { type: "transcript"; text: string }
  | {
      type: "result"
      score: number | null
      feedback: string | null
      is_follow_up: boolean
      complete: boolean
      question: string | null
      category: QuestionCategory | null
      question_index: number
      total_questions: number
    }
  | { type: "audio_start"; chunk_count: number }
  | { type: "audio_end" }
  | { type: "nudge" }
  | { type: "error"; detail: string }
