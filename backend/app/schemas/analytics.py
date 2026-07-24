import uuid
from datetime import datetime

from pydantic import BaseModel


class RagasRunResponse(BaseModel):
    run_id: uuid.UUID
    sample_size: int
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_precision: float
    avg_context_recall: float
    alert_triggered: bool


class DriftRunResponse(BaseModel):
    report_id: uuid.UUID
    baseline_size: int
    current_size: int
    psi_score: float
    alert_triggered: bool
    psi_threshold: float


class JudgeRunResponse(BaseModel):
    run_id: uuid.UUID
    sample_size: int
    agreement_rate: float
    avg_absolute_score_diff: float
    alert_triggered: bool


class RagasTrendPoint(BaseModel):
    run_id: uuid.UUID
    created_at: datetime
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_precision: float
    avg_context_recall: float
    alert_triggered: bool


class DriftAlertItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    psi_score: float
    alert_triggered: bool
    baseline_size: int
    current_size: int


class RagasAlertItem(BaseModel):
    run_id: uuid.UUID
    created_at: datetime
    avg_faithfulness: float


class AnalyticsDashboardResponse(BaseModel):
    total_pipeline_runs: int
    avg_match_score: float | None
    total_llm_cost_usd: float
    cost_per_hire_usd: float | None
    hired_count: int
    ragas_trend: list[RagasTrendPoint]
    recent_drift_reports: list[DriftAlertItem]
    recent_ragas_alerts: list[RagasAlertItem]
