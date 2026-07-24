import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_recruiter
from app.models.candidate import Candidate, CandidateStatus
from app.models.mlops import DriftReport, RagEvalLog
from app.schemas.analytics import (
    AnalyticsDashboardResponse,
    DriftAlertItem,
    DriftRunResponse,
    JudgeRunResponse,
    RagasAlertItem,
    RagasRunResponse,
    RagasTrendPoint,
)
from app.services import llm_router
from app.services.mlops import drift_detector, experiment_tracker, llm_judge_evaluator, ragas_evaluator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"], dependencies=[Depends(get_current_recruiter)])


@router.post("/mlops/ragas/run", response_model=RagasRunResponse)
async def trigger_ragas_run(sample_size: int = 5, db: AsyncSession = Depends(get_db)) -> RagasRunResponse:
    """Manually triggers a RAGAS evaluation run — the same function
    app.services.mlops.scheduler runs on a recurring background schedule when
    MLOPS_SCHEDULE_ENABLED=true (see .env.example)."""
    try:
        summary = await ragas_evaluator.run_evaluation(db, sample_size=sample_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RagasRunResponse(**{k: v for k, v in summary.items() if k != "rows"})


@router.post("/mlops/drift/run", response_model=DriftRunResponse)
async def trigger_drift_run(
    baseline_size: int = drift_detector.DEFAULT_BASELINE_SIZE,
    current_size: int = drift_detector.DEFAULT_CURRENT_SIZE,
    db: AsyncSession = Depends(get_db),
) -> DriftRunResponse:
    try:
        report = await drift_detector.run_drift_check(db, baseline_size=baseline_size, current_size=current_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DriftRunResponse(
        report_id=report["report_id"],
        baseline_size=report["baseline_size"],
        current_size=report["current_size"],
        psi_score=report["psi_score"],
        alert_triggered=report["alert_triggered"],
        psi_threshold=report["psi_threshold"],
    )


@router.post("/mlops/judge/run", response_model=JudgeRunResponse)
async def trigger_judge_run(sample_size: int = 5, db: AsyncSession = Depends(get_db)) -> JudgeRunResponse:
    """Manually triggers an LLM-as-judge run: an independent, deliberately
    stronger model blind-rescoring a sample of already-scored interview
    answers, to catch scoring bias/drift in the live-interview scoring model."""
    try:
        summary = await llm_judge_evaluator.run_evaluation(db, sample_size=sample_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JudgeRunResponse(**{k: v for k, v in summary.items() if k != "rows"})


@router.get("/analytics/dashboard", response_model=AnalyticsDashboardResponse)
async def get_analytics_dashboard(db: AsyncSession = Depends(get_db)) -> AnalyticsDashboardResponse:
    pipeline_stats = await experiment_tracker.get_pipeline_run_stats()
    total_cost = await llm_router.get_total_cost()

    hired_count = (
        await db.execute(select(func.count()).select_from(Candidate).where(Candidate.status == CandidateStatus.HIRED))
    ).scalar_one()
    cost_per_hire = (total_cost / hired_count) if hired_count else None

    trend_stmt = (
        select(
            RagEvalLog.run_id,
            func.min(RagEvalLog.created_at).label("created_at"),
            func.avg(RagEvalLog.faithfulness).label("avg_faithfulness"),
            func.avg(RagEvalLog.answer_relevancy).label("avg_answer_relevancy"),
            func.avg(RagEvalLog.context_precision).label("avg_context_precision"),
            func.avg(RagEvalLog.context_recall).label("avg_context_recall"),
            func.bool_or(RagEvalLog.alert_triggered).label("alert_triggered"),
        )
        .group_by(RagEvalLog.run_id)
        .order_by(func.min(RagEvalLog.created_at).desc())
        .limit(20)
    )
    trend_rows = (await db.execute(trend_stmt)).all()
    ragas_trend = [RagasTrendPoint(**row._mapping) for row in reversed(trend_rows)]

    alert_trend_rows = [row for row in trend_rows if row.alert_triggered][:10]
    recent_ragas_alerts = [
        RagasAlertItem(run_id=row.run_id, created_at=row.created_at, avg_faithfulness=row.avg_faithfulness)
        for row in alert_trend_rows
    ]

    drift_stmt = select(DriftReport).order_by(DriftReport.created_at.desc()).limit(10)
    drift_rows = (await db.execute(drift_stmt)).scalars().all()
    recent_drift_reports = [
        DriftAlertItem(
            id=d.id,
            created_at=d.created_at,
            psi_score=d.psi_score,
            alert_triggered=d.alert_triggered,
            baseline_size=d.baseline_size,
            current_size=d.current_size,
        )
        for d in drift_rows
    ]

    return AnalyticsDashboardResponse(
        total_pipeline_runs=pipeline_stats["count"],
        avg_match_score=pipeline_stats["avg_match_score"],
        total_llm_cost_usd=total_cost,
        cost_per_hire_usd=cost_per_hire,
        hired_count=hired_count,
        ragas_trend=ragas_trend,
        recent_drift_reports=recent_drift_reports,
        recent_ragas_alerts=recent_ragas_alerts,
    )
