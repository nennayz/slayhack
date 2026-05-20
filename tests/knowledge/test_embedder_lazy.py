from __future__ import annotations
import sys
import types
from knowledge.embedder import openai_embed_fn


def test_openai_embed_fn_does_not_construct_client_until_called(monkeypatch):
    constructed = {"count": 0}

    class FakeOpenAI:
        def __init__(self, api_key=""):
            constructed["count"] += 1
            if not api_key:
                raise RuntimeError("would have failed: missing credentials")

    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    embed_fn = openai_embed_fn("test-model", "")  # empty key — must NOT raise here
    assert callable(embed_fn)
    assert constructed["count"] == 0              # client not yet created
