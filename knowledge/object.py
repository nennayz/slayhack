from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field

KNOWN_KINDS = ("trend", "idea", "plan", "article", "image", "video", "caption")
STATUS_VALUES = ("new", "approved", "done", "archived", "rejected")


def make_uid(
    page: str,
    kind: str,
    created_at: datetime,
    dedup_text: str,
    taken: set[str] | None = None,
) -> str:
    """Build a stable, collision-checked uid: <page>-<kind>-<YYYYMMDD>-<hashN>."""
    taken = taken or set()
    date = created_at.strftime("%Y%m%d")
    digest = hashlib.sha256(dedup_text.encode("utf-8")).hexdigest()
    for length in range(4, len(digest) + 1):
        uid = f"{page}-{kind}-{date}-{digest[:length]}"
        if uid not in taken:
            return uid
    raise ValueError("could not generate a unique uid")


class ContentObject(BaseModel):
    """The shared contract for every artifact in the content pipeline."""

    page: str
    kind: str  # open string; KNOWN_KINDS is advisory only
    title: str
    summary: str = ""
    body: str = ""
    dedup_text: str
    status: str = "new"
    parent_uids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    uid: str = ""
    vault_path: str = ""
    asset_path: str | None = None

    def assign_uid(self, taken: set[str] | None = None) -> str:
        """Set self.uid (if empty) from page/kind/created_at/dedup_text."""
        if not self.uid:
            self.uid = make_uid(
                self.page, self.kind, self.created_at, self.dedup_text, taken=taken
            )
        return self.uid
