from fastapi import APIRouter

from app.api.v1.routes import (
    analytics,
    auth,
    candidates,
    dashboard,
    interview,
    jobs,
    matching,
    notifications,
    pipeline,
    report,
    resume,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(resume.router)
api_router.include_router(jobs.router)
api_router.include_router(matching.router)
api_router.include_router(pipeline.router)
api_router.include_router(interview.router)
api_router.include_router(interview.ws_router)
api_router.include_router(report.router)
api_router.include_router(analytics.router)
api_router.include_router(candidates.router)
api_router.include_router(dashboard.router)
api_router.include_router(notifications.router)
