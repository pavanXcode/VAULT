"""
API router aggregation.
Assembles all endpoint routers into a unified APIRouter.
"""

from fastapi import APIRouter
from backend.api.endpoints import documents, experiments, ground_truth, health, jobs, llm, system

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(documents.router)
api_router.include_router(experiments.router)
api_router.include_router(ground_truth.router)
api_router.include_router(llm.router)
api_router.include_router(jobs.router)
