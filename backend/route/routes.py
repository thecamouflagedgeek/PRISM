from fastapi import APIRouter

from route.consent import router as consent_router
from route.upload import router as upload_router
from route.validation import router as validation_router
from route.features import router as features_router
from route.fraud import router as fraud_router
from route.scoring import router as scoring_router
from route.explain import router as explain_router
from route.dashboard import router as dashboard_router
from route.bank_routes import router as bank_router
from route.salary_routes import router as salary_router
from route.utility_routes import router as utility_router


router=APIRouter()
router.include_router(consent_router)
router.include_router(upload_router)
router.include_router(validation_router)
router.include_router(features_router)
router.include_router(fraud_router)
router.include_router(scoring_router)
router.include_router(explain_router)
router.include_router(dashboard_router)
router.include_router(bank_router)
router.include_router(salary_router)
router.include_router(utility_router)