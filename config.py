from __future__ import annotations
import os
from dataclasses import dataclass


class MissingAPIKeyError(Exception):
    pass


@dataclass
class Config:
    brave_search_api_key: str
    openai_api_key: str
    openai_robin_model: str = "gpt-4o"
    openai_agent_model: str = "gpt-4o-mini"
    google_cloud_project: str = ""
    google_application_credentials: str = ""
    google_drive_manual_kits_folder_id: str = ""
    meta_access_token: str = ""
    meta_page_id: str = ""
    meta_ig_user_id: str = ""
    public_base_url: str = ""
    tiktok_access_token: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "nayzfreedom-scout/1.0"
    scout_timezone: str = "America/New_York"
    scout_seed_categories: str = ""   # comma-separated, parsed at use time
    scout_drive_folder_id: str = ""

    @classmethod
    def from_env(cls) -> Config:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if not openai_key:
            raise MissingAPIKeyError("OPENAI_API_KEY is required")
        return cls(
            brave_search_api_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
            openai_api_key=openai_key,
            openai_robin_model=os.getenv("OPENAI_ROBIN_MODEL", "gpt-4o"),
            openai_agent_model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
            google_application_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
            google_drive_manual_kits_folder_id=os.getenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", ""),
            meta_access_token=os.getenv("META_ACCESS_TOKEN", ""),
            meta_page_id=os.getenv("META_PAGE_ID", ""),
            meta_ig_user_id=os.getenv("META_IG_USER_ID", ""),
            public_base_url=os.getenv("PUBLIC_BASE_URL", os.getenv("OPS_PUBLIC_BASE_URL", "https://fleet.nayzfreedom.cloud")),
            tiktok_access_token=os.getenv("TIKTOK_ACCESS_TOKEN", ""),
            youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
            youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
            youtube_refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
            reddit_client_id=os.getenv("REDDIT_CLIENT_ID", ""),
            reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
            reddit_user_agent=os.getenv("REDDIT_USER_AGENT", "nayzfreedom-scout/1.0"),
            scout_timezone=os.getenv("SCOUT_TIMEZONE", "America/New_York"),
            scout_seed_categories=os.getenv(
                "SCOUT_SEED_CATEGORIES",
                "clean beauty,quiet luxury,wellness,self care,personal finance for women,"
                "home aesthetic,sustainable fashion,mental health,career growth",
            ),
            scout_drive_folder_id=os.getenv("SCOUT_DRIVE_FOLDER_ID", ""),
        )
