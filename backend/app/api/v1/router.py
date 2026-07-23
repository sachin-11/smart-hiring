from fastapi import APIRouter

from app.api.v1.routes import jobs, matching, resume

api_router = APIRouter()
api_router.include_router(resume.router)
api_router.include_router(jobs.router)
api_router.include_router(matching.router)
