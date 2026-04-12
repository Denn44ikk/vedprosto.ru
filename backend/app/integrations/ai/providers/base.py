from abc import ABC, abstractmethod

from ..core.types import AiResult


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def text(self, model: str, prompt: str, **kwargs) -> AiResult:
        raise NotImplementedError

    @abstractmethod
    async def image(self, model: str, prompt: str, **kwargs) -> AiResult:
        raise NotImplementedError
