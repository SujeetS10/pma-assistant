"""xAI Grok client via the OpenAI-compatible API. The key never leaves the backend."""
from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """Raised with a user-safe message; never includes the API key."""


class LLM(Protocol):
    model: str

    def complete(self, system: str, messages: list[dict]) -> str: ...


class GrokClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0, max_retries: int = 2):
        if not api_key:
            raise LLMError("XAI_API_KEY is not set in the backend environment.")
        if not model:
            raise LLMError("GROK_MODEL is not set. Use a model ID available to your xAI account.")
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(
            api_key=api_key, base_url="https://api.x.ai/v1",
            timeout=timeout, max_retries=max_retries,
        )

    def complete(self, system: str, messages: list[dict], temperature: float = 0.2) -> str:
        import openai

        try:
            r = self._client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=[{"role": "system", "content": system}, *messages],
            )
        except openai.AuthenticationError as e:
            raise LLMError("xAI rejected the API key (401). Check XAI_API_KEY.") from e
        except openai.PermissionDeniedError as e:
            raise LLMError("xAI denied access (403) for this key or model.") from e
        except openai.NotFoundError as e:
            raise LLMError(f"Model '{self.model}' not found for your account (check GROK_MODEL).") from e
        except openai.RateLimitError as e:
            raise LLMError("xAI rate limit or quota reached (429). Try again shortly.") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise LLMError("Could not reach xAI (timeout/network). Try again.") from e
        except openai.APIStatusError as e:
            raise LLMError(f"xAI returned an error (HTTP {e.status_code}).") from e
        content = r.choices[0].message.content if r.choices else None
        if not content:
            raise LLMError("xAI returned an empty response.")
        return content
