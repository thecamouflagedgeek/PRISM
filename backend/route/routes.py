from fastapi import APIRouter

from route.consent import router as consent_router
from route.assessment_routes import router as assessment_router

router = APIRouter()

router.include_router(consent_router)
router.include_router(assessment_router)