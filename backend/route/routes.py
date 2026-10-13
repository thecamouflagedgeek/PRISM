from fastapi import APIRouter

from route.consent import router as consent_router
from route.assessment_routes import router as assessment_router
from route.experimental_assessment_routes import router as experimental_assessment_router
from route.bank_cashflow_routes import router as bank_cashflow_router
from auth.routes import router as auth_router
from route.lender_routes import router as lender_router
from route.demo_fixture_routes import router as demo_fixture_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(consent_router)
router.include_router(assessment_router)
router.include_router(experimental_assessment_router)
router.include_router(bank_cashflow_router)
router.include_router(lender_router)
router.include_router(demo_fixture_router)
