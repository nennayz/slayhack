from __future__ import annotations
import hashlib
from datetime import datetime
from knowledge.object import ContentObject, make_uid


def make_obj(**kw):
    base = dict(
        page="slayhack", kind="article", title="Quiet Luxury Basics",
        summary="An intro to quiet luxury.", body="Full body text.",
        dedup_text="Quiet Luxury Basics — an intro to quiet luxury.",
        created_at=datetime(2026, 5, 19, 10, 0, 0),
    )
    base.update(kw)
    return ContentObject(**base)


def test_make_uid_format():
    uid = make_uid("slayhack", "article", datetime(2026, 5, 19), "some text")
    assert uid.startswith("slayhack-article-20260519-")
    assert len(uid.split("-")[-1]) == 4


def test_make_uid_is_deterministic():
    a = make_uid("slayhack", "article", datetime(2026, 5, 19), "same text")
    b = make_uid("slayhack", "article", datetime(2026, 5, 19), "same text")
    assert a == b


def test_make_uid_collision_extends_hash():
    digest = hashlib.sha256("text two".encode()).hexdigest()
    short_uid = f"slayhack-idea-20260519-{digest[:4]}"
    taken = {short_uid}
    uid = make_uid("slayhack", "idea", datetime(2026, 5, 19), "text two", taken=taken)
    assert uid not in taken
    assert uid == f"slayhack-idea-20260519-{digest[:5]}"


def test_assign_uid_sets_uid():
    obj = make_obj()
    assert obj.uid == ""
    uid = obj.assign_uid()
    assert uid != ""
    assert obj.uid == uid


def test_assign_uid_is_idempotent():
    obj = make_obj()
    first = obj.assign_uid()
    second = obj.assign_uid()
    assert first == second


def test_content_object_defaults():
    obj = make_obj()
    assert obj.status == "new"
    assert obj.parent_uids == []
    assert obj.tags == []
    assert obj.asset_path is None
