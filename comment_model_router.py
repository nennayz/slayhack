from __future__ import annotations
import base64
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    provider: str  # "anthropic" | "openai" | "gemini"
    model: str


@dataclass
class ModelRouter:
    fallback_chain: list[ProviderConfig]
    anthropic_key: str = ""
    openai_key: str = ""
    gemini_key: str = ""

    def call(self, image_b64: str, system_prompt: str) -> tuple[str, str]:
        """Vision call. Try each provider in fallback_chain. Returns (text, model_label)."""
        errors: list[str] = []
        for cfg in self.fallback_chain:
            try:
                text = self._call_provider(cfg, image_b64, system_prompt)
                return text, f"{cfg.provider}/{cfg.model}"
            except Exception as exc:
                logger.warning("Provider %s/%s failed: %s", cfg.provider, cfg.model, exc)
                errors.append(f"{cfg.provider}/{cfg.model}: {exc}")
        raise RuntimeError("All providers failed:\n" + "\n".join(errors))

    def call_text(self, prompt: str) -> tuple[str, str]:
        """Text-only call (no image). Used for reply shortening. Returns (text, model_label)."""
        errors: list[str] = []
        for cfg in self.fallback_chain:
            try:
                text = self._call_provider_text(cfg, prompt)
                return text, f"{cfg.provider}/{cfg.model}"
            except Exception as exc:
                logger.warning("Provider %s/%s text failed: %s", cfg.provider, cfg.model, exc)
                errors.append(f"{cfg.provider}/{cfg.model}: {exc}")
        raise RuntimeError("All providers failed:\n" + "\n".join(errors))

    # ── Vision dispatchers ──────────────────────────────────────────────────

    def _call_provider(self, cfg: ProviderConfig, image_b64: str, system_prompt: str) -> str:
        if cfg.provider == "anthropic":
            return self._call_anthropic(cfg.model, image_b64, system_prompt)
        if cfg.provider == "openai":
            return self._call_openai(cfg.model, image_b64, system_prompt)
        if cfg.provider == "gemini":
            return self._call_gemini(cfg.model, image_b64, system_prompt)
        raise ValueError(f"Unknown provider: {cfg.provider!r}")

    def _call_anthropic(self, model: str, image_b64: str, system_prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                }],
            }],
        )
        return response.content[0].text

    def _call_openai(self, model: str, image_b64: str, system_prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    }],
                },
            ],
        )
        return response.choices[0].message.content

    def _call_gemini(self, model: str, image_b64: str, system_prompt: str) -> str:
        import google.generativeai as genai
        import PIL.Image
        import io
        genai.configure(api_key=self.gemini_key)
        gmodel = genai.GenerativeModel(model, system_instruction=system_prompt)
        image_bytes = base64.b64decode(image_b64)
        img = PIL.Image.open(io.BytesIO(image_bytes))
        response = gmodel.generate_content(img)
        return response.text

    # ── Text-only dispatchers ───────────────────────────────────────────────

    def _call_provider_text(self, cfg: ProviderConfig, prompt: str) -> str:
        if cfg.provider == "anthropic":
            return self._call_anthropic_text(cfg.model, prompt)
        if cfg.provider == "openai":
            return self._call_openai_text(cfg.model, prompt)
        if cfg.provider == "gemini":
            return self._call_gemini_text(cfg.model, prompt)
        raise ValueError(f"Unknown provider: {cfg.provider!r}")

    def _call_anthropic_text(self, model: str, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _call_openai_text(self, model: str, prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _call_gemini_text(self, model: str, prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.gemini_key)
        gmodel = genai.GenerativeModel(model)
        response = gmodel.generate_content(prompt)
        return response.text
