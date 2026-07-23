export type InterviewStatus = "scheduled" | "in_progress" | "completed" | "cancelled" | "no_show"
export type QuestionCategory = "technical" | "behavioral" | "situational" | "culture"

export interface InterviewStartResponse {
  session_id: string
  question: string
  category: QuestionCategory
  question_index: number
  total_questions: number
  audio_url: string | null
}

export interface InterviewAnswerResponse {
  session_id: string
  score: number
  feedback: string
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

/** Messages the /ws/interview/{sessionId} socket sends to the client. */
export type InterviewWsServerMessage =
  | { type: "transcript"; text: string }
  | {
      type: "result"
      score: number
      feedback: string
      is_follow_up: boolean
      complete: boolean
      question: string | null
      category: QuestionCategory | null
      question_index: number
      total_questions: number
    }
  | { type: "audio_start" }
  | { type: "error"; detail: string }
