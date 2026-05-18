from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import Config
from models.niche_opportunity import NicheSignal, ScoutJob, ScoutJobStatus

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_META_ADS_URL = "https://graph.facebook.com/v19.0/ads_archive"

_DRY_SIGNALS = [
    NicheSignal(niche_name="clean beauty", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 450000}),
    NicheSignal(niche_name="quiet luxury", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 320000}),
    NicheSignal(niche_name="wellness routine", raw_data={"source": "dry-run", "trend": "stable", "reddit_size": 890000}),
    NicheSignal(niche_name="sustainable fashion", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 210000}),
    NicheSignal(niche_name="personal finance women", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 560000}),
]


class ScoutAgent:
    def __init__(self, config: Config):
        self.config = config

    def run(self, job: ScoutJob, dry_run: bool = False) -> ScoutJob:
        job.status = ScoutJobStatus.RUNNING
        if dry_run:
            job.signals = list(_DRY_SIGNALS)
            return job
        return self._run_live(job)

    def _run_live(self, job: ScoutJob) -> ScoutJob:
        categories = [c.strip() for c in self.config.scout_seed_categories.split(",") if c.strip()]
        signals: list[NicheSignal] = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self._fetch_all_for_niche, cat): cat for cat in categories}
            for future in as_completed(futures):
                cat = futures[future]
                try:
                    sig = future.result()
                    signals.append(sig)
                except Exception as exc:
                    logger.warning("Scout fetch failed for %s: %s", cat, exc)

        job.signals = signals
        return job

    def _fetch_all_for_niche(self, niche: str) -> NicheSignal:
        raw: dict = {"niche": niche}
        raw["brave"] = self._fetch_brave(niche)
        raw["google_trends"] = self._fetch_google_trends(niche)
        raw["reddit"] = self._fetch_reddit(niche)
        raw["meta_ads"] = self._fetch_meta_ads(niche)
        return NicheSignal(niche_name=niche, raw_data=raw)

    def _fetch_brave(self, niche: str) -> list[dict]:
        if not self.config.brave_search_api_key:
            return []
        try:
            resp = requests.get(
                _BRAVE_URL,
                headers={"Accept": "application/json", "X-Subscription-Token": self.config.brave_search_api_key},
                params={"q": f"{niche} viral trend social media 2026", "count": 5},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", [])
            return [{"title": r.get("title", ""), "description": r.get("description", "")} for r in results[:5]]
        except Exception as exc:
            logger.warning("Brave Search failed for %s: %s", niche, exc)
            return []

    def _fetch_google_trends(self, niche: str) -> dict:
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-US", tz=300)
            pt.build_payload([niche], timeframe="today 3-m", geo="US")
            interest = pt.interest_over_time()
            if interest.empty:
                return {"trend_direction": "unknown"}
            values = interest[niche].tolist()
            if len(values) < 2:
                return {"trend_direction": "unknown", "recent": values[-1] if values else 0}
            direction = "rising" if values[-1] > values[0] else ("declining" if values[-1] < values[0] else "stable")
            return {"trend_direction": direction, "recent": int(values[-1]), "start": int(values[0])}
        except Exception as exc:
            logger.warning("Google Trends failed for %s: %s", niche, exc)
            return {"trend_direction": "unknown"}

    def _fetch_reddit(self, niche: str) -> dict:
        try:
            import praw
            if not self.config.reddit_client_id:
                return {}
            reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
            )
            results = []
            for sub in reddit.subreddits.search(niche, limit=3):
                results.append({
                    "name": sub.display_name,
                    "subscribers": sub.subscribers,
                    "description": str(sub.public_description)[:200],
                })
            return {"subreddits": results}
        except Exception as exc:
            logger.warning("Reddit fetch failed for %s: %s", niche, exc)
            return {}

    def _fetch_meta_ads(self, niche: str) -> dict:
        if not self.config.meta_access_token:
            return {}
        try:
            resp = requests.get(
                _META_ADS_URL,
                params={
                    "search_terms": niche,
                    "ad_reached_countries": '["US"]',
                    "ad_active_status": "ACTIVE",
                    "limit": 5,
                    "fields": "id,ad_creative_body,ad_snapshot_url",
                    "access_token": self.config.meta_access_token,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            ad_count = len(data.get("data", []))
            return {"active_ads": ad_count}
        except Exception as exc:
            logger.warning("Meta Ads fetch failed for %s: %s", niche, exc)
            return {}
