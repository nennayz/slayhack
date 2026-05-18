from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from comment_model_router import ModelRouter, ProviderConfig


def _make_router(chain=None):
    chain = chain or [
        ProviderConfig(provider="anthropic", model="claude-sonnet-4-6"),
        ProviderConfig(provider="openai", model="gpt-4o"),
        ProviderConfig(provider="gemini", model="gemini-2.0-flash"),
    ]
    return ModelRouter(
        fallback_chain=chain,
        anthropic_key="test-anthropic",
        openai_key="test-openai",
        gemini_key="test-gemini",
    )


def test_call_uses_first_provider_on_success():
    router = _make_router()
    with patch.object(router, "_call_anthropic", return_value="draft reply") as mock_a:
        text, label = router.call("base64img==", "system prompt")
    mock_a.assert_called_once_with("claude-sonnet-4-6", "base64img==", "system prompt")
    assert text == "draft reply"
    assert "anthropic" in label
    assert "claude-sonnet-4-6" in label


def test_call_falls_back_to_openai_when_anthropic_fails():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("429")), \
         patch.object(router, "_call_openai", return_value="openai reply") as mock_o:
        text, label = router.call("base64img==", "system prompt")
    mock_o.assert_called_once()
    assert text == "openai reply"
    assert "openai" in label


def test_call_falls_back_to_gemini_when_anthropic_and_openai_fail():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("quota")), \
         patch.object(router, "_call_openai", side_effect=Exception("quota")), \
         patch.object(router, "_call_gemini", return_value="gemini reply") as mock_g:
        text, label = router.call("base64img==", "system prompt")
    mock_g.assert_called_once()
    assert text == "gemini reply"
    assert "gemini" in label


def test_call_raises_when_all_providers_fail():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("err1")), \
         patch.object(router, "_call_openai", side_effect=Exception("err2")), \
         patch.object(router, "_call_gemini", side_effect=Exception("err3")):
        with pytest.raises(RuntimeError, match="All providers failed"):
            router.call("base64img==", "system prompt")


def test_call_text_uses_first_provider():
    router = _make_router()
    with patch.object(router, "_call_anthropic_text", return_value="short reply") as mock_a:
        text, label = router.call_text("shorten this")
    mock_a.assert_called_once_with("claude-sonnet-4-6", "shorten this")
    assert text == "short reply"


def test_call_text_falls_back():
    router = _make_router()
    with patch.object(router, "_call_anthropic_text", side_effect=Exception("quota")), \
         patch.object(router, "_call_openai_text", return_value="short openai") as mock_o:
        text, label = router.call_text("shorten this")
    assert text == "short openai"
    assert "openai" in label


def test_single_provider_chain():
    router = _make_router(chain=[ProviderConfig(provider="gemini", model="gemini-2.0-flash")])
    with patch.object(router, "_call_gemini", return_value="gemini only") as mock_g:
        text, label = router.call("img==", "prompt")
    assert text == "gemini only"
    assert "gemini" in label
