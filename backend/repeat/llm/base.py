"""Single LLM seam. Everything above this calls `complete_structured` and nothing else,
so swapping OpenAI for another provider is a one-file change."""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from ..config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when the model call fails or returns something the schema rejects."""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T: ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "narration.webm") -> str: ...


@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    if s.llm_is_live:
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=s.openai_api_key or "", model=s.openai_model)
    from .mock_provider import MockProvider

    return MockProvider()
