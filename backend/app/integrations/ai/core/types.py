from dataclasses import dataclass, field
from typing import Any

# Default profile names you can keep in profiles.yaml.
# Gateway also supports any custom profile names.
DEFAULT_PROFILE_NAMES = ("text_exp", "text_cheap", "image_exp", "image_cheap")
ProfileName = str


@dataclass
class AiResult:
    text: str | None = None
    image_url: str | None = None
    provider: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1
    latency_ms: float | None = None
    fallback_used: bool = False
    raw: Any = None
