from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import AppSettings
from ...integrations.ai.service import AIIntegrationService
from ...integrations.ifcg import IfcgService
from ...integrations.its import ITSService
from ...integrations.sigma import SigmaService
from ...interfaces.ui_api.workspace_service import WorkspaceService
from ...storage.knowledge.catalogs import TnvedCatalogService
from ..core import ChatSession
from .base_case_agent import BaseCaseAgentScenario


class UICaseAgentScenario(BaseCaseAgentScenario):
    _transcript_filename = "agent_cli.json"
    _context_filename = "agent_cli_context.md"

    def __init__(
        self,
        *,
        settings: AppSettings,
        ai_integration_service: AIIntegrationService,
        case_workspace_service: WorkspaceService,
        tnved_catalog_service: TnvedCatalogService | None = None,
        ifcg_service: IfcgService | None = None,
        sigma_service: SigmaService | None = None,
        its_service: ITSService | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            ai_integration_service=ai_integration_service,
            tnved_catalog_service=tnved_catalog_service,
            ifcg_service=ifcg_service,
            sigma_service=sigma_service,
            its_service=its_service,
        )
        self.case_workspace_service = case_workspace_service

    @property
    def channel_label(self) -> str:
        return "ui_case_agent"

    def resolve_runtime_context(self, *, case_id: str | None = None) -> dict[str, Any]:
        return self.case_workspace_service.resolve_case_runtime_context(case_id)

    def _build_session(self, runtime_context: dict[str, Any]) -> ChatSession:
        case_id = str(runtime_context["case_id"])
        case_dir = Path(str(runtime_context["case_dir"]))
        return ChatSession(
            session_key=f"ui:case_agent:{case_id}",
            case_id=case_id,
            case_dir=case_dir,
            transcript_path=case_dir / "work" / self._transcript_filename,
            context_path=case_dir / "work" / self._context_filename,
            mode="ui_case_agent",
            transcript_mode="ui_case_agent",
            web_search_mode="auto",
            intro_text=(
                f"Case agent готов по кейсу {case_id}. "
                "Можно спрашивать свободно про код, риски, альтернативы, IFCG, Sigma, ITS и внешний ресерч."
            ),
        )
