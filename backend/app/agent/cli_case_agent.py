from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ..config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal case agent over one case folder.")
    parser.add_argument("--case-dir", required=True, help="Absolute or relative path to one case directory")
    parser.add_argument("--message", default="", help="Single message mode. If omitted, interactive mode starts.")
    parser.add_argument("--show-history", action="store_true", help="Print current transcript before asking")
    return parser.parse_args()


def print_history(payload: dict[str, object]) -> None:
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    print(f"case_id: {payload.get('case_id', '')}")
    print(f"case_dir: {payload.get('case_dir', '')}")
    print(f"context_file: {payload.get('context_file', '')}")
    print(f"transcript_file: {payload.get('transcript_file', '')}")
    print("")
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip() or "unknown"
        text = str(item.get("text", "")).strip()
        print(f"[{role}] {text}")
        print("")


async def interactive_loop(*, scenario, case_dir: Path) -> int:
    history = await scenario.get_history_async(case_dir=case_dir)
    print_history(history)
    print("Команды: /exit, /quit, /history")
    while True:
        try:
            message = input("case-agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0
        if not message:
            continue
        if message.lower() in {"/exit", "/quit"}:
            return 0
        if message.lower() == "/history":
            print_history(await scenario.get_history_async(case_dir=case_dir))
            continue
        payload = await scenario.send_message_async(case_dir=case_dir, message=message)
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        last_message = messages[-1] if messages else {}
        answer = str(last_message.get("text", "")).strip() if isinstance(last_message, dict) else ""
        print("")
        print(answer or "Пустой ответ.")
        print("")


async def main_async() -> int:
    args = parse_args()
    settings = get_settings()
    from ..container import build_container
    from .scenarios.terminal_case_agent import TerminalCaseAgentScenario

    container = build_container()
    scenario = TerminalCaseAgentScenario(
        settings=settings,
        ai_integration_service=container.ai_integration_service,
        tnved_catalog_service=container.tnved_catalog_service,
        ifcg_service=container.ifcg_service,
        sigma_service=container.sigma_service,
        its_service=container.its_service,
    )
    case_dir = Path(args.case_dir).expanduser().resolve()

    if args.show_history:
        print_history(await scenario.get_history_async(case_dir=case_dir))
        if not args.message:
            return 0

    if args.message:
        payload = await scenario.send_message_async(case_dir=case_dir, message=args.message)
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        last_message = messages[-1] if messages else {}
        answer = str(last_message.get("text", "")).strip() if isinstance(last_message, dict) else ""
        print(answer)
        return 0

    return await interactive_loop(scenario=scenario, case_dir=case_dir)


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
