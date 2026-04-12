from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...config import AppSettings
from ...integrations.ai.service import AIIntegrationService
from ...integrations.ifcg import IfcgService
from ...integrations.its import ITSService
from ...integrations.sigma import SigmaService
from ...storage.knowledge.catalogs import TnvedCatalogService
from ..core import ChatSession
from .base_case_agent import BaseCaseAgentScenario


class TGCaseAgentScenario(BaseCaseAgentScenario):
    def __init__(
        self,
        *,
        settings: AppSettings,
        ai_integration_service: AIIntegrationService,
        runtime_context_provider: Callable[..., dict[str, Any]] | None = None,
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
        self.runtime_context_provider = runtime_context_provider

    @property
    def channel_label(self) -> str:
        return "tg_case_agent"

    def resolve_runtime_context(self, *args, **kwargs) -> dict[str, Any]:
        if self.runtime_context_provider is None:
            raise NotImplementedError("Telegram case agent is not wired yet, but it must use the shared base_case_agent flow.")
        return self.runtime_context_provider(*args, **kwargs)

    def _build_session(self, runtime_context: dict[str, Any]) -> ChatSession:
        case_id = str(runtime_context["case_id"])
        case_dir = Path(str(runtime_context["case_dir"]))
        return ChatSession(
            session_key=f"tg:case_agent:{case_id}",
            case_id=case_id,
            case_dir=case_dir,
            transcript_path=case_dir / "work" / "agent_tg.json",
            context_path=case_dir / "work" / "agent_tg_context.md",
            mode="tg_case_agent",
            transcript_mode="tg_case_agent",
            web_search_mode="auto",
            intro_text=(
                f"Telegram case agent готов по кейсу {case_id}. "
                "Можно спрашивать про код, альтернативы, риски и внешние подтверждения."
            ),
        )
