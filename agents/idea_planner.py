from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from models.idea_plan_job import IdeaDraft

if TYPE_CHECKING:
    import openai

    from config import Config

logger = logging.getLogger(__name__)


class _LazyOpenAIClientProxy:
    """Proxy that constructs the OpenAI client on first real SDK access."""

    def __init__(self, agent: "IdeaPlannerAgent") -> None:
        self._agent = agent

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._agent._get_client(), name)


_DRY_IDEAS: list[IdeaDraft] = [
    IdeaDraft(title="The Invisible Lip Liner Hack", hook="POV: your lips last all day", angle="Tutorial", content_type="video"),
    IdeaDraft(title="Quiet Luxury Morning Routine", hook="This is how rich girls start their day", angle="Lifestyle", content_type="image"),
    IdeaDraft(title="5 Dupes That Beat the Original", hook="Stop wasting money on pricey formulas", angle="Review", content_type="article"),
    IdeaDraft(title="The 3-Step Kiss-Proof Secret", hook="omg why didn't anyone tell me sooner", angle="Tutorial", content_type="video"),
    IdeaDraft(title="Get Ready With Me: Date Night", hook="come get ready with me for date night", angle="GRWM", content_type="infographic"),
    IdeaDraft(title="The 60-Second Glow Up Method", hook="this hack changed my whole face", angle="Tutorial", content_type="video"),
    IdeaDraft(title="Why Your Skincare Order Matters", hook="you've been doing this wrong forever", angle="Educational", content_type="article"),
]

_SYSTEM_PROMPT = """\
You are an expert social media content strategist for {page_slug}. \
Generate exactly 7 distinct content ideas based on the trend signals and brand profile provided. \
Each idea must be unique in topic and angle. Return a JSON array (no markdown fences) of 7 objects with these exact keys:
  title        (string, ≤ 60 chars)
  hook         (string, the opening line / scroll-stopper)
  angle        (string, e.g. Tutorial, Review, Lifestyle, GRWM, Educational)
  content_type (string, one of: video, image, article, infographic)

Return ONLY the JSON array. No preamble. No markdown."""

_USER_PROMPT = """\
Brand profile:
{brand_summary}

Recent trend signals (use at least 3 as inspiration):
{signals_summary}

Recent ideas already generated (avoid repeating these angles):
{recent_ideas_summary}

Generate 7 fresh, diverse content ideas now."""


class IdeaPlannerAgent:
    """Standalone LLM agent for daily idea generation. Does NOT subclass BaseAgent."""

    def __init__(self, config: "Config") -> None:
        self.config = config
        self._client: "openai.OpenAI | None" = None

    def __getattr__(self, name: str) -> Any:
        if name == "client":
            return _LazyOpenAIClientProxy(self)
        raise AttributeError(name)

    def _get_client(self) -> "openai.OpenAI":
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self.config.openai_api_key)
        return self._client

    def generate(
        self,
        signals: list[dict[str, Any]],
        recent_ideas: list[dict[str, Any]],
        brand: dict[str, Any],
        dry_run: bool = False,
    ) -> list[IdeaDraft]:
        if dry_run:
            return list(_DRY_IDEAS)
        return self._generate_live(signals, recent_ideas, brand)

    def _generate_live(
        self,
        signals: list[dict[str, Any]],
        recent_ideas: list[dict[str, Any]],
        brand: dict[str, Any],
    ) -> list[IdeaDraft]:
        page_slug = brand.get("page_slug", "unknown")
        brand_summary = (
            f"Mission: {brand.get('mission', 'N/A')}\n"
            f"Tone: {brand.get('tone', 'N/A')}\n"
            f"Target audience: {brand.get('target_audience', 'N/A')}\n"
            f"Script style: {brand.get('script_style', 'N/A')}"
        )
        if signals:
            signals_summary = "\n".join(
                f"- {s.get('title', s.get('topic', 'unknown'))} (direction: {s.get('direction', '?')}, score: {float(s.get('score', 0)):.1f})"
                for s in signals[:10]
            )
        else:
            logger.warning("IdeaPlanner: no trend signals available — using brand-only context")
            signals_summary = "(No trend signals available — generate ideas from brand profile only)"

        recent_ideas_summary = (
            "\n".join(f"- {i.get('title', '?')}" for i in recent_ideas[:30])
            or "(No recent ideas)"
        )

        system_msg = _SYSTEM_PROMPT.format(page_slug=page_slug)
        user_msg = _USER_PROMPT.format(
            brand_summary=brand_summary,
            signals_summary=signals_summary,
            recent_ideas_summary=recent_ideas_summary,
        )

        try:
            resp = self.client.chat.completions.create(
                model=getattr(self.config, "openai_agent_model", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.8,
            )
            content = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error("IdeaPlannerAgent LLM call failed: %s", exc)
            return []

        drafts = self._parse_ideas(content)
        if len(drafts) < 7:
            logger.warning("IdeaPlanner: LLM returned %d ideas (expected 7)", len(drafts))
        return drafts

    def _parse_ideas(self, text: str) -> list[IdeaDraft]:
        """Extract IdeaDraft list from LLM JSON response. Returns [] on total failure."""
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            raw = json.loads(text)
            if not isinstance(raw, list):
                raw = [raw]
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("IdeaPlanner: failed to parse JSON from LLM: %s", exc)
            return []

        drafts: list[IdeaDraft] = []
        for item in raw:
            try:
                drafts.append(IdeaDraft(
                    title=str(item["title"])[:60],
                    hook=str(item["hook"]),
                    angle=str(item["angle"]),
                    content_type=str(item["content_type"]),
                ))
            except (KeyError, TypeError) as exc:
                logger.warning("IdeaPlanner: skipping malformed idea item: %s", exc)
        return drafts
