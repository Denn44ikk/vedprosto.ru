from __future__ import annotations

from ...agent.scenarios.ui_case_agent import UICaseAgentScenario


class AgentCliService:
    def __init__(self, *, ui_case_agent_scenario: UICaseAgentScenario) -> None:
        self.ui_case_agent_scenario = ui_case_agent_scenario

    def get_history(self, case_id: str | None = None) -> dict[str, object]:
        return self.ui_case_agent_scenario.get_history(case_id=case_id)

    def send_message(self, *, case_id: str | None, message: str) -> dict[str, object]:
        return self.ui_case_agent_scenario.send_message(case_id=case_id, message=message)

    async def get_history_async(self, case_id: str | None = None) -> dict[str, object]:
        return await self.ui_case_agent_scenario.get_history_async(case_id=case_id)

    async def send_message_async(self, *, case_id: str | None, message: str) -> dict[str, object]:
        return await self.ui_case_agent_scenario.send_message_async(case_id=case_id, message=message)
