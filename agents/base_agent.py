from __future__ import annotations
import random
import time
from abc import ABC, abstractmethod
import anthropic
from anthropic import Anthropic
from config import Config
from models.content_job import ContentJob

TEAM_IDENTITY = "You are part of Freedom Architects, the content team at NayzFreedom.\n\n"


class BaseAgent(ABC):
    def __init__(self, config: Config):
        self.config = config
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.model = "claude-sonnet-4-6"

    def run(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.dry_run:
            return self.run_dry(job, **kwargs)
        return self.run_live(job, **kwargs)

    @abstractmethod
    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        pass

    @abstractmethod
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        pass

    def _call_claude(self, system: str, user: str, max_tokens: int = 2048) -> str:
        from anthropic.types import TextBlock
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}],
                )
                for block in response.content:
                    if isinstance(block, TextBlock):
                        return block.text
                raise ValueError("No text block in Claude response")
            except anthropic.RateLimitError as exc:
                last_exc = exc
                if attempt == 3:
                    raise
                time.sleep((2 ** attempt) + random.random())
            except anthropic.APIStatusError as exc:
                last_exc = exc
                if exc.status_code in (500, 529) and attempt < 3:
                    time.sleep((2 ** attempt) + random.random())
                else:
                    raise
            except anthropic.APIConnectionError as exc:
                last_exc = exc
                if attempt < 3:
                    time.sleep((2 ** attempt) + random.random())
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    def _parse_json(self, raw: str) -> dict | list:
        import json
        import re
        candidate = raw.strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(f"Agent received invalid JSON from Claude: {e}\nRaw: {raw[:200]}")
