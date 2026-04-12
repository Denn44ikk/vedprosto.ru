from __future__ import annotations

from fastapi import APIRouter

from .agent_cli import router as agent_cli_router
from .auth import router as auth_router
from .chat_cli import router as chat_cli_router
from .eco_fee import router as eco_fee_router
from .health import router as health_router
from .its_session import router as its_session_router
from .jobs import router as jobs_router
from .workbook import router as workbook_router
from .workspace import router as workspace_router


router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(eco_fee_router)
router.include_router(agent_cli_router)
router.include_router(chat_cli_router)
router.include_router(its_session_router)
router.include_router(workbook_router)
router.include_router(jobs_router)
router.include_router(workspace_router)
