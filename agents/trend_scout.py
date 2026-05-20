from __future__ import annotations
import logging
import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

import requests

from config import Config
from models.trend_scan_job import TrendHit

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_GTRENDS_LOCK = threading.Lock()

_DRY_HITS: list[TrendHit] = [
    TrendHit(topic="beauty hacks",     direction="rising",  score=82.0, sources={"source": "dry-run"}),
    TrendHit(topic="skincare routine", direction="stable",  score=71.5, sources={"source": "dry-run"}),
    TrendHit(topic="makeup tutorial",  direction="rising",  score=68.0, sources={"source": "dry-run"}),
    TrendHit(topic="Gen Z fashion",    direction="rising",  score=55.0, sources={"source": "dry-run"}),
    TrendHit(topic="wellness routine", direction="stable",  score=48.0, sources={"source": "dry-run"}),
]


class TrendScoutAgent:
    def __init__(self, config: Config) -> None:
        self.config = config

    def scan(self, seed_topics: list[str], dry_run: bool = False) -> list[TrendHit]:
        if dry_run:
            return list(_DRY_HITS)
        return self._scan_live(seed_topics)

    def _scan_live(self, seed_topics: list[str]) -> list[TrendHit]:
        brave_results: dict[str, list[dict]] = {}
        reddit_results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            brave_futs: dict[Future[list[dict]], str] = {
                executor.submit(self._fetch_brave, t): t for t in seed_topics
            }
            reddit_futs: dict[Future[dict], str] = {
                executor.submit(self._fetch_reddit, t): t for t in seed_topics
            }
            for brave_future in as_completed(brave_futs):
                brave_results[brave_futs[brave_future]] = brave_future.result()
            for reddit_future in as_completed(reddit_futs):
                reddit_results[reddit_futs[reddit_future]] = reddit_future.result()

        hits: list[TrendHit] = []
        for topic in seed_topics:
            gtrends = self._fetch_google_trends(topic)
            brave = brave_results.get(topic, [])
            reddit = reddit_results.get(topic, {})
            score = self._compute_score(brave, gtrends, reddit)
            hits.append(TrendHit(
                topic=topic,
                direction=gtrends.get("trend_direction", "unknown"),
                score=score,
                sources={"brave": brave, "gtrends": gtrends, "reddit": reddit},
            ))
        return hits

    def _compute_score(self, brave: list[dict], gtrends: dict, reddit: dict) -> float:
        brave_count = min(len(brave), 10)
        gtrends_score = float(gtrends.get("recent", 0))
        subs = sum(s.get("subscribers", 0) for s in (reddit.get("subreddits") or []))
        reddit_score = math.log10(subs + 1) * 20
        raw = brave_count * 0.4 + gtrends_score * 0.4 + reddit_score * 0.2
        return max(0.0, min(100.0, raw))

    def _fetch_brave(self, topic: str) -> list[dict]:
        if not self.config.brave_search_api_key:
            return []
        try:
            resp = requests.get(
                _BRAVE_URL,
                headers={"Accept": "application/json",
                         "X-Subscription-Token": self.config.brave_search_api_key},
                params={"q": f"{topic} viral trend 2026", "count": "10"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", [])
            return [{"title": r.get("title", ""), "description": r.get("description", "")}
                    for r in results[:10]]
        except Exception as exc:
            logger.warning("Brave Search failed for %s: %s", topic, exc)
            return []

    def _fetch_google_trends(self, topic: str) -> dict:
        try:
            from pytrends.request import TrendReq
            with _GTRENDS_LOCK:
                time.sleep(2)
                pt = TrendReq(hl="en-US", tz=300)
                pt.build_payload([topic], timeframe="today 3-m", geo="US")
                interest = pt.interest_over_time()
            if interest.empty:
                return {"trend_direction": "unknown"}
            values = interest[topic].tolist()
            if len(values) < 2:
                return {"trend_direction": "unknown", "recent": values[-1] if values else 0}
            direction = ("rising" if values[-1] > values[0]
                         else "declining" if values[-1] < values[0] else "stable")
            return {"trend_direction": direction, "recent": int(values[-1]), "start": int(values[0])}
        except Exception as exc:
            logger.warning("Google Trends failed for %s: %s", topic, exc)
            return {"trend_direction": "unknown"}

    def _fetch_reddit(self, topic: str) -> dict:
        if not self.config.reddit_client_id:
            return {}
        try:
            import praw
            reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
            )
            results = [
                {"name": sub.display_name, "subscribers": sub.subscribers}
                for sub in reddit.subreddits.search(topic, limit=3)
            ]
            return {"subreddits": results}
        except Exception as exc:
            logger.warning("Reddit failed for %s: %s", topic, exc)
            return {}
