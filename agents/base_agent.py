from __future__ import annotations
import random
import time
from abc import ABC, abstractmethod
import openai
from openai import OpenAI
from config import Config
from models.content_job import ContentJob

TEAM_IDENTITY = "You are part of Freedom Architects, the content team at NayzFreedom.\n\n"


class BaseAgent(ABC):
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.openai_agent_model

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
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                text = response.choices[0].message.content
                if text:
                    return text
                raise ValueError("No text content in OpenAI response")
            except openai.RateLimitError as exc:
                last_exc = exc
                if attempt == 3:
                    raise
                time.sleep((2 ** attempt) + random.random())
            except openai.APIStatusError as exc:
                last_exc = exc
                if exc.status_code in (500, 502, 503, 504, 529) and attempt < 3:
                    time.sleep((2 ** attempt) + random.random())
                else:
                    raise
            except openai.APIConnectionError as exc:
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
            raise ValueError(f"Agent received invalid JSON from OpenAI: {e}\nRaw: {raw[:200]}")
