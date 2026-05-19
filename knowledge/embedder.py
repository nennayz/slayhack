from __future__ import annotations

from collections.abc import Callable, Sequence

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


class OfflineError(Exception):
    """Raised when embeddings cannot be produced because the network is down."""


def openai_embed_fn(model: str, api_key: str) -> EmbedFn:
    """Build a real embed function backed by the OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _embed(texts: Sequence[str]) -> list[list[float]]:
        resp = client.embeddings.create(model=model, input=list(texts))
        return [d.embedding for d in resp.data]

    return _embed


class Embedder:
    """Turns text into vectors. Offline-safe: network failures raise OfflineError."""

    def __init__(self, model: str, embed_fn: EmbedFn) -> None:
        self.model = model
        self._embed_fn = embed_fn

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            return self._embed_fn(texts)
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise OfflineError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — API errors also degrade gracefully
            raise OfflineError(str(exc)) from exc
