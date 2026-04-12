from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from typing import Any

from ...config import AppSettings
from ...integrations.ai.service import AIIntegrationService
from ...integrations.ifcg import IfcgService
from ...integrations.its import ITSService
from ...integrations.sigma import SigmaService
from ...storage.knowledge.catalogs import TnvedCatalogService
from ..core import (
    ChatAttachments,
    ChatContextStore,
    ChatEngine,
    ChatResponse,
    ChatSession,
    ChatSessionStore,
    ChatTranscriptMessage,
)
from ..research import AgentWebSearchService
from ..tools import CaseAgentToolbox
from .case_context_builder import CaseAgentContextBuilder


class BaseCaseAgentScenario(ABC):
    def __init__(
        self,
        *,
        settings: AppSettings,
        ai_integration_service: AIIntegrationService,
        tnved_catalog_service: TnvedCatalogService | None = None,
        ifcg_service: IfcgService | None = None,
        sigma_service: SigmaService | None = None,
        its_service: ITSService | None = None,
    ) -> None:
        self.settings = settings
        self.session_store = ChatSessionStore()
        self.context_store = ChatContextStore()
        self.attachments = ChatAttachments()
        self.engine = ChatEngine(ai_integration_service=ai_integration_service)
        self.web_search_service = AgentWebSearchService(settings=settings)
        self.case_context_builder = CaseAgentContextBuilder(attachments=self.attachments)
        self.toolbox = CaseAgentToolbox(
            tnved_catalog_service=tnved_catalog_service,
            ifcg_service=ifcg_service,
            sigma_service=sigma_service,
            its_service=its_service,
            web_search_service=self.web_search_service,
        )

    @property
    @abstractmethod
    def channel_label(self) -> str:
        raise NotImplementedError

    def get_history(self, *args, **kwargs) -> dict[str, object]:
        return asyncio.run(self.get_history_async(*args, **kwargs))

    async def get_history_async(self, *args, **kwargs) -> dict[str, object]:
        runtime_context = self.resolve_runtime_context(*args, **kwargs)
        session = self._build_session(runtime_context)
        messages = self.session_store.ensure_intro(session, self.session_store.load_transcript(session))
        recent_messages = self.session_store.trim(messages, limit=self.settings.chat_cli_history_limit)
        runtime_context = await self._with_agent_context(runtime_context=runtime_context, recent_messages=recent_messages)
        self.context_store.write_context_packet(
            session,
            self.case_context_builder.build(
                runtime_context=runtime_context,
                recent_messages=recent_messages,
                channel_label=self.channel_label,
            ),
        )
        return self._build_response(session, messages).as_dict()

    def send_message(self, *args, **kwargs) -> dict[str, object]:
        return asyncio.run(self.send_message_async(*args, **kwargs))

    async def send_message_async(self, *args, **kwargs) -> dict[str, object]:
        message = str(kwargs.pop("message", "")).strip()
        runtime_context = self.resolve_runtime_context(*args, **kwargs)
        session = self._build_session(runtime_context)
        messages = self.session_store.ensure_intro(session, self.session_store.load_transcript(session))
        messages.append(
            ChatTranscriptMessage(
                role="user",
                text=message,
                created_at=self.session_store.now_iso(),
            )
        )
        recent_messages = self.session_store.trim(messages, limit=self.settings.chat_cli_history_limit)
        runtime_context = await self._with_agent_context(runtime_context=runtime_context, recent_messages=recent_messages)
        context_packet = self.case_context_builder.build(
            runtime_context=runtime_context,
            recent_messages=recent_messages,
            channel_label=self.channel_label,
        )
        self.context_store.write_context_packet(session, context_packet)

        answer = await self._run_case_agent(
            runtime_context=runtime_context,
            session=session,
            context_markdown=context_packet.markdown,
            recent_messages=recent_messages,
        )
        messages.append(
            ChatTranscriptMessage(
                role="model",
                text=answer,
                created_at=self.session_store.now_iso(),
            )
        )
        self.session_store.save_transcript(session, messages=messages)

        recent_messages = self.session_store.trim(messages, limit=self.settings.chat_cli_history_limit)
        self.context_store.write_context_packet(
            session,
            self.case_context_builder.build(
                runtime_context=await self._with_agent_context(runtime_context=runtime_context, recent_messages=recent_messages),
                recent_messages=recent_messages,
                channel_label=self.channel_label,
            ),
        )
        return self._build_response(session, messages).as_dict()

    @abstractmethod
    def resolve_runtime_context(self, *args, **kwargs) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _build_session(self, runtime_context: dict[str, Any]) -> ChatSession:
        raise NotImplementedError

    @staticmethod
    def _system_prompt() -> str:
        return "\n".join(
            [
                "Ты работаешь как свободный case-aware агент по подбору кода ТН ВЭД.",
                "Ты не wizard и не простой чат, а консультант-исследователь.",
                "У тебя есть контекст кейса, изображения, результаты pipeline и tool-digests по Python-модулям проекта.",
                "Если для ответа хватает case и готовых сигналов, не трать ресурсы зря.",
                "Если вопрос требует проверки, опирайся на приложенные digests: catalog, IFCG, Sigma, ITS, web research.",
                "Сначала используй внутренний case и структурные сигналы, потом внешние исследования.",
                "Не придумывай факты. Четко разделяй: что подтверждено, что вероятно, что требует ручной проверки.",
                "Твоя задача: помочь человеку самому выбрать код и понять риски ошибки.",
                "Отвечай по-русски, коротко, но содержательно.",
                "Структура ответа:",
                "Вывод:",
                "Основания:",
                "Риски / альтернативы:",
                "Что проверить дальше:",
            ]
        )

    async def _run_case_agent(
        self,
        *,
        runtime_context: dict[str, Any],
        session: ChatSession,
        context_markdown: str,
        recent_messages: list[ChatTranscriptMessage],
    ) -> str:
        attachment_blocks = self.attachments.build_case_image_blocks(runtime_context)
        try:
            return await self.engine.run_async(
                profile=self.settings.chat_cli_ai_profile,
                use_fallback=self.settings.chat_cli_use_fallback,
                system_prompt=self._system_prompt(),
                context_markdown=context_markdown,
                recent_messages=recent_messages,
                intro_text=session.intro_text,
                attachment_blocks=attachment_blocks,
            )
        except Exception:
            if not attachment_blocks:
                raise
            return await self.engine.run_async(
                profile=self.settings.chat_cli_ai_profile,
                use_fallback=self.settings.chat_cli_use_fallback,
                system_prompt=self._system_prompt(),
                context_markdown=context_markdown,
                recent_messages=recent_messages,
                intro_text=session.intro_text,
                attachment_blocks=None,
            )

    @staticmethod
    def _build_response(session: ChatSession, messages: list[ChatTranscriptMessage]) -> ChatResponse:
        return ChatResponse(
            case_id=session.case_id,
            case_dir=str(session.case_dir),
            context_file=str(session.context_path),
            transcript_file=str(session.transcript_path),
            mode=session.mode,
            web_search_mode=session.web_search_mode,
            messages=[message.as_dict() for message in messages],
        )

    async def _with_agent_context(
        self,
        *,
        runtime_context: dict[str, Any],
        recent_messages: list[ChatTranscriptMessage],
    ) -> dict[str, Any]:
        latest_user_message = ""
        for message in reversed(recent_messages):
            if message.role == "user" and message.text.strip():
                latest_user_message = message.text.strip()
                break

        enriched = dict(runtime_context)
        if latest_user_message:
            web_task = asyncio.create_task(
                self.web_search_service.search_async(
                    runtime_context=runtime_context,
                    latest_user_message=latest_user_message,
                )
            )
            tools_task = asyncio.create_task(
                self.toolbox.build_payload_async(
                    runtime_context=runtime_context,
                    latest_user_message=latest_user_message,
                )
            )
            web_result, tools_result = await asyncio.gather(web_task, tools_task, return_exceptions=True)
            enriched["web_research_payload"] = (
                web_result if not isinstance(web_result, Exception) else {"status": "error", "query": "", "results": [], "note": str(web_result)}
            )
            enriched["agent_tools_payload"] = (
                tools_result if not isinstance(tools_result, Exception) else {"status": "error", "reason": str(tools_result), "live_reads": {}}
            )
        else:
            enriched["web_research_payload"] = {"status": "idle", "query": "", "results": [], "note": "no user query yet"}
            enriched["agent_tools_payload"] = self.toolbox.build_payload(
                runtime_context=runtime_context,
                latest_user_message=latest_user_message,
            )
        return enriched
