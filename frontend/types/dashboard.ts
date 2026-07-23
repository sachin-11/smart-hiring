export interface DashboardStats {
  total_candidates: number
  active_jds: number
  avg_match_score: number | null
  interviews_scheduled: number
}

export interface ActivityItem {
  id: string
  type: string
  description: string
  timestamp: string
}

export interface DashboardActivityResponse {
  items: ActivityItem[]
}
