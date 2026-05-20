from __future__ import annotations
from datetime import datetime
from typing import Any, cast
import requests
from agents.base_agent import BaseAgent, TEAM_IDENTITY
from models.content_job import ContentJob

_DRY_RUN_DATA = {
    "trends": ["Glossy lips that don't budge", "Quiet luxury skincare", "5-minute GRWM"],
    "trending_sounds": ["Espresso - Sabrina Carpenter", "Apple - Charli xcx"],
    "formats": ["POV", "Get ready with me", "Before & after"],
    "source": "dry-run mock",
}

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class MiaAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        job.trend_data = _DRY_RUN_DATA
        job.stage = "mia_done"
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        query = f"{job.brief} trend {' '.join(job.platforms)} {datetime.now().year}"
        params: dict[str, str | int] = {"q": query, "count": 10}
        resp = requests.get(
            _BRAVE_SEARCH_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": self.config.brave_search_api_key},
            params=params,
        )
        resp.raise_for_status()
        search_results = resp.json()

        snippets = "\n".join(
            f"- {r['title']}: {r.get('description', '')}"
            for r in search_results.get("web", {}).get("results", [])[:5]
        )
        system = (
            TEAM_IDENTITY +
            f"You are Mia, a trend researcher for {job.pm.page_name}. "
            f"Target audience: {job.pm.brand.target_audience}. "
            f"Platforms: {', '.join(job.platforms)}."
        )
        user = (
            f"Brief: {job.brief}\n\nSearch results:\n{snippets}\n\n"
            "Return a JSON object with keys: trends (list of str), "
            "trending_sounds (list of str), formats (list of str). JSON only."
        )
        raw = self._call_claude(system, user)
        parsed = self._parse_json(raw)
        job.trend_data = cast(dict[str, Any], parsed)
        job.stage = "mia_done"
        return job
