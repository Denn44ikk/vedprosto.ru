from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


class ChatAttachments:
    def build_case_image_blocks(
        self,
        runtime_context: dict[str, Any],
        *,
        max_images: int = 4,
        detail: str = "high",
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for image_path in self._case_image_paths(runtime_context)[: max(0, max_images)]:
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._to_data_uri(image_path),
                        "detail": detail,
                    },
                }
            )
        return blocks

    def image_names(self, runtime_context: dict[str, Any], *, max_images: int = 10) -> list[str]:
        names: list[str] = []
        for path in self._case_image_paths(runtime_context)[: max(0, max_images)]:
            names.append(path.name)
        return names

    def _case_image_paths(self, runtime_context: dict[str, Any]) -> list[Path]:
        case_dir_value = runtime_context.get("case_dir")
        if not isinstance(case_dir_value, str) or not case_dir_value.strip():
            return []

        case_dir = Path(case_dir_value)
        case_payload = runtime_context.get("case_payload") if isinstance(runtime_context.get("case_payload"), dict) else {}
        raw_image_files = case_payload.get("image_files") if isinstance(case_payload.get("image_files"), list) else []

        paths: list[Path] = []
        for raw_item in raw_image_files:
            image_name = Path(str(raw_item)).name
            if not image_name:
                continue
            image_path = case_dir / "images" / image_name
            if image_path.exists() and image_path.is_file():
                paths.append(image_path)
        return paths

    @staticmethod
    def _to_data_uri(path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(path.name)
        if not mime_type:
            mime_type = "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
