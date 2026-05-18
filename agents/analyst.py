from __future__ import annotations
import json
import logging
import re

from openai import OpenAI

from config import Config
from models.niche_opportunity import NicheOpportunity, NicheSignal, ScoutJob, ScoutJobStatus

logger = logging.getLogger(__name__)

_DRY_OPPORTUNITIES = [
    NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 22-38, ingredient-conscious, IG-native",
        platforms=["instagram", "tiktok"],
        reach_score=91.0,
        trend_direction="rising",
        content_formats=["reel", "carousel", "infographic"],
        monetization_notes="High affiliate potential (skincare), e-book: 'Your Clean Routine'",
        signals={"source": "dry-run"},
    ),
    NicheOpportunity(
        niche_name="quiet luxury",
        target_audience="Women USA 25-40, aspirational minimalists",
        platforms=["instagram", "tiktok", "youtube"],
        reach_score=85.0,
        trend_direction="rising",
        content_formats=["reel", "ootd", "listicle"],
        monetization_notes="LTK affiliate, e-book: 'Dress Like Old Money'",
        signals={"source": "dry-run"},
    ),
    NicheOpportunity(
        niche_name="personal finance women",
        target_audience="Women USA 25-40, income earners building wealth",
        platforms=["tiktok", "instagram", "youtube"],
        reach_score=79.0,
        trend_direction="rising",
        content_formats=["explainer", "infographic", "series"],
        monetization_notes="High CPM, e-book: 'Your First $10K'",
        signals={"source": "dry-run"},
    ),
]


class AnalystAgent:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.openai_agent_model

    def run(self, job: ScoutJob, dry_run: bool = False) -> ScoutJob:
        if dry_run:
            job.opportunities = sorted(_DRY_OPPORTUNITIES, key=lambda o: o.reach_score, reverse=True)
            job.status = ScoutJobStatus.AWAITING_APPROVAL
            return job
        return self._run_live(job)

    def _run_live(self, job: ScoutJob) -> ScoutJob:
        if not job.signals:
            raise ValueError("AnalystAgent._run_live requires job.signals to be non-empty")
        signals_text = "\n\n".join(
            f"Niche: {s.niche_name}\nData: {json.dumps(s.raw_data, ensure_ascii=False)}"
            for s in job.signals
        )
        system = (
            "You are Analyst, a market intelligence agent for NayzFreedom Fleet. "
            "Your job: score and rank niche opportunities for new social media pages "
            "targeting women in the USA, ages 18-44. Priority: REACH first (viral potential, "
            "audience growth speed), then monetization. Content must fit the Fleet's "
            "production capabilities (short video, image, infographic, article)."
        )
        user = (
            f"Raw niche signals:\n\n{signals_text}\n\n"
            "Return a JSON array of the top 5 opportunities, each with:\n"
            "niche_name, target_audience, platforms (list), reach_score (0-100 float), "
            "trend_direction ('rising'|'stable'|'declining'), content_formats (list), "
            "monetization_notes (str), signals (dict summary). "
            "Sort by reach_score descending. JSON array only, no markdown."
        )
        raw = self._call_openai(system, user)
        parsed = self._parse_json(raw)
        from pydantic import ValidationError
        opportunities = []
        for item in parsed:
            try:
                opportunities.append(NicheOpportunity(**item))
            except ValidationError as exc:
                logger.warning("Analyst: skipping malformed opportunity from OpenAI: %s", exc)
        job.opportunities = opportunities
        job.status = ScoutJobStatus.AWAITING_APPROVAL
        return job

    def _call_openai(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _parse_json(self, raw: str) -> list:
        candidate = raw.strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
        return json.loads(candidate)
