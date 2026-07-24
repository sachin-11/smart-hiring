export interface RagasRunResponse {
  run_id: string
  sample_size: number
  avg_faithfulness: number
  avg_answer_relevancy: number
  avg_context_precision: number
  avg_context_recall: number
  alert_triggered: boolean
}

export interface DriftRunResponse {
  report_id: string
  baseline_size: number
  current_size: number
  psi_score: number
  alert_triggered: boolean
  psi_threshold: number
}

export interface RagasTrendPoint {
  run_id: string
  created_at: string
  avg_faithfulness: number
  avg_answer_relevancy: number
  avg_context_precision: number
  avg_context_recall: number
  alert_triggered: boolean
}

export interface DriftAlertItem {
  id: string
  created_at: string
  psi_score: number
  alert_triggered: boolean
  baseline_size: number
  current_size: number
}

export interface RagasAlertItem {
  run_id: string
  created_at: string
  avg_faithfulness: number
}

export interface JudgeRunResponse {
  run_id: string
  sample_size: number
  agreement_rate: number
  avg_absolute_score_diff: number
  alert_triggered: boolean
}

export interface AnalyticsDashboardResponse {
  total_pipeline_runs: number
  avg_match_score: number | null
  total_llm_cost_usd: number
  cost_per_hire_usd: number | null
  hired_count: number
  ragas_trend: RagasTrendPoint[]
  recent_drift_reports: DriftAlertItem[]
  recent_ragas_alerts: RagasAlertItem[]
}
