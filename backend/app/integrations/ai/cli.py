from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .gateway import AiGateway
from .core.types import AiResult
from .settings import get_ai_settings


def _base_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if getattr(args, "temperature", None) is not None:
        kwargs["temperature"] = args.temperature
    if getattr(args, "max_tokens", None) is not None:
        kwargs["max_tokens"] = args.max_tokens
    if getattr(args, "top_p", None) is not None:
        kwargs["top_p"] = args.top_p
    return kwargs


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _result_to_data(result: AiResult) -> dict[str, Any]:
    return asdict(result)


def _load_prompts(args: argparse.Namespace) -> list[str]:
    prompts: list[str] = []
    if getattr(args, "prompt", None):
        prompts.extend(args.prompt)
    if getattr(args, "file", None):
        lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        prompts.extend([line for line in lines if line.strip()])
    return prompts


def _build_gateway(args: argparse.Namespace) -> AiGateway:
    env_file = str(args.env_file).strip() if getattr(args, "env_file", None) else ""
    if env_file:
        load_dotenv(env_file)
    else:
        ai_settings = get_ai_settings()
        if ai_settings.default_env_file.exists():
            load_dotenv(ai_settings.default_env_file)
        else:
            load_dotenv()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    return AiGateway(profiles_path=args.profiles, max_concurrency=args.max_concurrency)


def _add_fallback_argument(parser: argparse.ArgumentParser, *, default: bool) -> None:
    parser.add_argument(
        "--fallback",
        dest="use_fallback",
        action=argparse.BooleanOptionalAction,
        default=default,
        help="Enable or disable profile fallback",
    )


async def _run_text(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    kwargs = _base_kwargs(args)
    if args.use_fallback:
        result = await gateway.text_with_fallback(args.profile, args.prompt, **kwargs)
    else:
        result = await gateway.text(args.profile, args.prompt, **kwargs)

    if args.raw:
        print(_to_json(result.raw))
    elif args.result_json:
        print(_to_json(_result_to_data(result)))
    else:
        print(result.text or "")
    return 0


async def _run_image(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    kwargs = _base_kwargs(args)
    if args.size:
        kwargs["size"] = args.size

    if args.use_fallback:
        result = await gateway.image_with_fallback(args.profile, args.prompt, **kwargs)
    else:
        result = await gateway.image(args.profile, args.prompt, **kwargs)

    if args.raw:
        print(_to_json(result.raw))
    elif args.result_json:
        print(_to_json(_result_to_data(result)))
    else:
        print(result.image_url or "")
    return 0


async def _run_chat(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    messages = json.loads(Path(args.messages_file).read_text(encoding="utf-8"))
    if not isinstance(messages, list):
        raise ValueError("messages-file must contain a JSON array of chat messages")
    kwargs = _base_kwargs(args)

    if args.use_fallback:
        result = await gateway.chat_with_fallback(args.profile, messages, **kwargs)
    else:
        result = await gateway.chat(args.profile, messages, **kwargs)

    if args.raw:
        print(_to_json(result.raw))
    elif args.result_json:
        print(_to_json(_result_to_data(result)))
    else:
        print(result.text or "")
    return 0


async def _run_batch(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    kwargs = _base_kwargs(args)
    prompts = _load_prompts(args)
    if not prompts:
        raise ValueError("Provide at least one --prompt or --file with prompts")

    if args.kind == "text":
        results = await gateway.text_many(
            args.profile,
            prompts,
            use_fallback=args.use_fallback,
            concurrency=args.concurrency,
            **kwargs,
        )
    else:
        if args.size:
            kwargs["size"] = args.size
        results = await gateway.image_many(
            args.profile,
            prompts,
            use_fallback=args.use_fallback,
            concurrency=args.concurrency,
            **kwargs,
        )

    output: list[dict[str, Any]] = []
    has_errors = False
    for index, item in enumerate(results):
        if isinstance(item, Exception):
            has_errors = True
            output.append(
                {
                    "index": index,
                    "ok": False,
                    "error_type": item.__class__.__name__,
                    "error": str(item),
                }
            )
        else:
            payload: Any
            if args.raw:
                payload = item.raw
            elif args.result_json:
                payload = _result_to_data(item)
            else:
                payload = item.text if args.kind == "text" else item.image_url
            output.append({"index": index, "ok": True, "result": payload})

    print(_to_json(output))
    if has_errors and args.fail_on_error:
        return 1
    return 0


async def _run_json(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    kwargs = _base_kwargs(args)
    schema = None
    if args.schema_file:
        schema = json.loads(Path(args.schema_file).read_text(encoding="utf-8"))
    data = await gateway.text_json(
        args.profile,
        args.prompt,
        use_fallback=args.use_fallback,
        schema=schema,
        strict=not args.no_strict,
        **kwargs,
    )
    print(_to_json(data))
    return 0


async def _run_ocr(args: argparse.Namespace) -> int:
    gateway = _build_gateway(args)
    kwargs = _base_kwargs(args)
    result = await gateway.ocr(
        args.profile,
        image=args.image,
        mode=args.mode,
        prompt=args.prompt,
        detail=args.detail,
        use_fallback=args.use_fallback,
        **kwargs,
    )

    if args.mode == "json":
        print(_to_json(gateway.extract_json(result)))
    elif args.raw:
        print(_to_json(result.raw))
    elif args.result_json:
        print(_to_json(_result_to_data(result)))
    else:
        print(result.text or "")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ai_settings = get_ai_settings()
    parser = argparse.ArgumentParser(prog="ai-connector", description="CLI for ai_connector local gateway")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profiles", default=str(ai_settings.profiles_path), help="Path to profiles.yaml")
    common.add_argument("--env-file", default=str(ai_settings.default_env_file), help="Path to .env file")
    common.add_argument("--log-level", default=ai_settings.cli_log_level, help="DEBUG/INFO/WARNING/ERROR")
    common.add_argument(
        "--max-concurrency",
        type=int,
        default=ai_settings.max_concurrency,
        help="Default max concurrency for batch execution",
    )

    text = subparsers.add_parser("text", parents=[common], help="Send one text request")
    text.add_argument("--profile", default=ai_settings.cli_profile)
    text.add_argument("--prompt", required=True)
    text.add_argument("--temperature", type=float, default=None)
    text.add_argument("--max-tokens", type=int, default=None)
    text.add_argument("--top-p", type=float, default=None)
    _add_fallback_argument(text, default=ai_settings.cli_use_fallback)
    text.add_argument("--result-json", action="store_true", help="Print AiResult as JSON")
    text.add_argument("--raw", action="store_true", help="Print provider raw JSON")

    image = subparsers.add_parser("image", parents=[common], help="Generate one image")
    image.add_argument("--profile", default=ai_settings.cli_profile)
    image.add_argument("--prompt", required=True)
    image.add_argument("--size", default=None, help="Image size, e.g. 1024x1024")
    _add_fallback_argument(image, default=ai_settings.cli_use_fallback)
    image.add_argument("--result-json", action="store_true")
    image.add_argument("--raw", action="store_true")

    chat = subparsers.add_parser("chat", parents=[common], help="Run custom chat/multimodal messages payload")
    chat.add_argument("--profile", default=ai_settings.cli_profile)
    chat.add_argument("--messages-file", required=True, help="Path to JSON array of messages")
    chat.add_argument("--temperature", type=float, default=None)
    chat.add_argument("--max-tokens", type=int, default=None)
    chat.add_argument("--top-p", type=float, default=None)
    _add_fallback_argument(chat, default=ai_settings.cli_use_fallback)
    chat.add_argument("--result-json", action="store_true")
    chat.add_argument("--raw", action="store_true")

    batch = subparsers.add_parser("batch", parents=[common], help="Run batch text/image requests")
    batch.add_argument("--kind", choices=["text", "image"], default="text")
    batch.add_argument("--profile", default=ai_settings.cli_profile)
    batch.add_argument("--prompt", action="append", default=[], help="Prompt value, can be repeated")
    batch.add_argument("--file", default=None, help="File with one prompt per line")
    batch.add_argument("--concurrency", type=int, default=ai_settings.max_concurrency)
    batch.add_argument("--temperature", type=float, default=None)
    batch.add_argument("--max-tokens", type=int, default=None)
    batch.add_argument("--top-p", type=float, default=None)
    batch.add_argument("--size", default=None, help="For image batch")
    _add_fallback_argument(batch, default=ai_settings.cli_use_fallback)
    batch.add_argument("--fail-on-error", action="store_true", help="Return exit code 1 if any item failed")
    batch.add_argument("--result-json", action="store_true")
    batch.add_argument("--raw", action="store_true")

    as_json = subparsers.add_parser("json", parents=[common], help="Request structured JSON output")
    as_json.add_argument("--profile", default=ai_settings.cli_profile)
    as_json.add_argument("--prompt", required=True)
    as_json.add_argument("--schema-file", default=None, help="Path to JSON schema file")
    as_json.add_argument("--no-strict", action="store_true")
    as_json.add_argument("--temperature", type=float, default=None)
    as_json.add_argument("--max-tokens", type=int, default=None)
    as_json.add_argument("--top-p", type=float, default=None)
    _add_fallback_argument(as_json, default=ai_settings.cli_use_fallback)

    ocr = subparsers.add_parser("ocr", parents=[common], help="Run OCR via vision-capable model")
    ocr.add_argument("--profile", default=ai_settings.cli_profile)
    ocr.add_argument("--image", required=True, help="Image URL, data URI, or local file path")
    ocr.add_argument("--mode", choices=["plain", "markdown", "json"], default="plain")
    ocr.add_argument("--prompt", default=None)
    ocr.add_argument("--detail", choices=["low", "high", "auto"], default=None, help="Vision detail level")
    ocr.add_argument("--temperature", type=float, default=None)
    ocr.add_argument("--max-tokens", type=int, default=None)
    ocr.add_argument("--top-p", type=float, default=None)
    _add_fallback_argument(ocr, default=ai_settings.cli_use_fallback)
    ocr.add_argument("--result-json", action="store_true")
    ocr.add_argument("--raw", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "text":
        return asyncio.run(_run_text(args))
    if args.command == "image":
        return asyncio.run(_run_image(args))
    if args.command == "chat":
        return asyncio.run(_run_chat(args))
    if args.command == "batch":
        return asyncio.run(_run_batch(args))
    if args.command == "json":
        return asyncio.run(_run_json(args))
    if args.command == "ocr":
        return asyncio.run(_run_ocr(args))
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
