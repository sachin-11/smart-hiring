export interface MatchResult {
  candidate_id: string
  name: string | null
  match_score: number
  skill_overlap: string[]
  missing_skills: string[]
  explanation: string
}

export interface MatchResponse {
  jd_id: string
  results: MatchResult[]
}
