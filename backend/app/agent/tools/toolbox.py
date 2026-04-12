from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from ...integrations.ifcg import IfcgService
from ...integrations.its import ITSService
from ...integrations.sigma import SigmaService
from ...storage.knowledge.catalogs import TnvedCatalogService
from ..research import AgentWebSearchService
from .case_reader_tool import CaseReaderTool
from .ifcg_tool import IfcgTool
from .its_tool import ItsTool
from .sigma_tool import SigmaTool
from .tnved_catalog_tool import TnvedCatalogTool
from .web_search_tool import WebSearchTool


_SIGMA_HINT_RE = re.compile(r"(sigma|пошлин|пошл|ставк|ндс|стп)", re.IGNORECASE)
_ITS_HINT_RE = re.compile(r"(its|итс|цена|стоим|срок|дата)", re.IGNORECASE)
_IFCG_HINT_RE = re.compile(r"(ifcg|ифцг|ветк|декл|подтверд)", re.IGNORECASE)


@dataclass
class CaseAgentToolbox:
    tnved_catalog_service: TnvedCatalogService | None
    ifcg_service: IfcgService | None
    sigma_service: SigmaService | None
    its_service: ITSService | None
    web_search_service: AgentWebSearchService

    def __post_init__(self) -> None:
        self.case_reader_tool = CaseReaderTool()
        self.catalog_tool = TnvedCatalogTool(catalog_service=self.tnved_catalog_service)
        self.ifcg_tool = IfcgTool(ifcg_service=self.ifcg_service)
        self.sigma_tool = SigmaTool(sigma_service=self.sigma_service)
        self.its_tool = ItsTool(its_service=self.its_service)
        self.web_search_tool = WebSearchTool(web_search_service=self.web_search_service)

    def build_payload(
        self,
        *,
        runtime_context: dict[str, Any],
        latest_user_message: str,
    ) -> dict[str, Any]:
        codes = self.case_reader_tool.extract_relevant_codes(runtime_context)
        payload: dict[str, Any] = {
            "status": "ok",
            "available_tools": {
                "case_reader": True,
                "tnved_catalog": self.tnved_catalog_service is not None,
                "ifcg": self.ifcg_service is not None,
                "sigma": self.sigma_service is not None,
                "its": self.its_service is not None,
                "web_search": True,
            },
            "case_digest": self.case_reader_tool.build_case_digest(runtime_context),
            "relevant_codes": codes,
            "catalog": self.catalog_tool.describe_codes(codes),
            "case_ifcg": self.ifcg_tool.read_case_signal(runtime_context),
            "live_reads": {},
        }
        message = latest_user_message.strip()
        if not message:
            return payload
        if _SIGMA_HINT_RE.search(message):
            payload["live_reads"]["sigma"] = self.sigma_tool.fetch_codes(codes[:3])
        if _ITS_HINT_RE.search(message):
            payload["live_reads"]["its"] = self.its_tool.fetch_codes(codes[:3])
        if _IFCG_HINT_RE.search(message):
            payload["live_reads"]["ifcg"] = self.ifcg_tool.run_discovery_from_case(runtime_context)
        return payload

    async def build_payload_async(
        self,
        *,
        runtime_context: dict[str, Any],
        latest_user_message: str,
    ) -> dict[str, Any]:
        codes = self.case_reader_tool.extract_relevant_codes(runtime_context)
        payload: dict[str, Any] = {
            "status": "ok",
            "available_tools": {
                "case_reader": True,
                "tnved_catalog": self.tnved_catalog_service is not None,
                "ifcg": self.ifcg_service is not None,
                "sigma": self.sigma_service is not None,
                "its": self.its_service is not None,
                "web_search": True,
            },
            "case_digest": self.case_reader_tool.build_case_digest(runtime_context),
            "relevant_codes": codes,
            "catalog": self.catalog_tool.describe_codes(codes),
            "case_ifcg": self.ifcg_tool.read_case_signal(runtime_context),
            "live_reads": {},
        }
        message = latest_user_message.strip()
        if not message:
            return payload

        tasks: dict[str, asyncio.Future | asyncio.Task] = {}
        if _SIGMA_HINT_RE.search(message):
            tasks["sigma"] = asyncio.create_task(self.sigma_tool.fetch_codes_async(codes[:3]))
        if _ITS_HINT_RE.search(message):
            tasks["its"] = asyncio.create_task(self.its_tool.fetch_codes_async(codes[:3]))
        if _IFCG_HINT_RE.search(message):
            tasks["ifcg"] = asyncio.create_task(self.ifcg_tool.run_discovery_from_case_async(runtime_context))

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for key, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    payload["live_reads"][key] = {"status": "error", "reason": str(result)}
                else:
                    payload["live_reads"][key] = result
        return payload
