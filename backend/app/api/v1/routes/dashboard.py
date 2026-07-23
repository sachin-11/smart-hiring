from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Application, Job, JobStatus
from app.models.report import Report
from app.schemas.dashboard import ActivityItem, DashboardActivityResponse, DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    total_candidates = (await db.execute(select(func.count()).select_from(Candidate))).scalar_one()
    active_jds = (
        await db.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN))
    ).scalar_one()
    avg_match_score = (await db.execute(select(func.avg(Application.match_score)))).scalar_one()
    # This app starts interviews immediately rather than scheduling them for later
    # (Module 5 has no separate "scheduled" step), so every Interview row represents
    # one that's been set up — that's the meaningful count here, not just status=SCHEDULED.
    interviews_scheduled = (await db.execute(select(func.count()).select_from(Interview))).scalar_one()

    return DashboardStats(
        total_candidates=total_candidates,
        active_jds=active_jds,
        avg_match_score=float(avg_match_score) if avg_match_score is not None else None,
        interviews_scheduled=interviews_scheduled,
    )


@router.get("/activity", response_model=DashboardActivityResponse)
async def get_dashboard_activity(db: AsyncSession = Depends(get_db)) -> DashboardActivityResponse:
    items: list[ActivityItem] = []

    candidates = (
        await db.execute(select(Candidate).order_by(Candidate.created_at.desc()).limit(10))
    ).scalars().all()
    for c in candidates:
        items.append(
            ActivityItem(
                id=c.id,
                type="candidate_added",
                description=f"{c.full_name or 'A candidate'} was added to the pipeline",
                timestamp=c.created_at,
            )
        )

    jobs = (await db.execute(select(Job).order_by(Job.created_at.desc()).limit(10))).scalars().all()
    for j in jobs:
        items.append(
            ActivityItem(id=j.id, type="job_created", description=f"Job posted: {j.title}", timestamp=j.created_at)
        )

    interviews = (
        await db.execute(select(Interview).order_by(Interview.updated_at.desc()).limit(10))
    ).scalars().all()
    for i in interviews:
        items.append(
            ActivityItem(
                id=i.id,
                type="interview_" + i.status.value,
                description=f"Interview {i.status.value.replace('_', ' ')}",
                timestamp=i.updated_at,
            )
        )

    reports = (await db.execute(select(Report).order_by(Report.created_at.desc()).limit(10))).scalars().all()
    for r in reports:
        items.append(
            ActivityItem(
                id=r.id,
                type="report_generated",
                description=f"Scorecard generated: {r.recommendation}",
                timestamp=r.created_at,
            )
        )

    items.sort(key=lambda i: i.timestamp, reverse=True)
    return DashboardActivityResponse(items=items[:20])
