"""OpenAI structured outputs. One retry on schema rejection, then a clean LLMError."""

from __future__ import annotations

import io
import logging
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .base import LLMError, LLMProvider

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        last: Exception | None = None
        for attempt in range(2):
            try:
                resp = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=schema,
                )
                parsed = resp.choices[0].message.parsed
                if parsed is None:
                    raise LLMError("model returned no parsed output (refusal or empty)")
                return parsed
            except ValidationError as e:
                last = e
                log.warning("structured output rejected by schema (attempt %d): %s", attempt, e)
            except Exception as e:  # network, auth, rate limit
                last = e
                log.warning("openai call failed (attempt %d): %s", attempt, e)
        raise LLMError(f"OpenAI call failed after retry: {last}")

    async def transcribe(self, audio_bytes: bytes, filename: str = "narration.webm") -> str:
        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        try:
            resp = await self.client.audio.transcriptions.create(model="whisper-1", file=buf)
        except Exception as e:
            raise LLMError(f"transcription failed: {e}") from e
        return resp.text.strip()
