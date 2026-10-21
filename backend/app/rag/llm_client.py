"""OpenAI-compatible chat client (Groq by default; xAI, OpenAI, etc. via LLM_BASE_URL).

The API key stays in the backend and is never echoed in error messages.
"""
from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse


class LLMError(Exception):
    """Raised with a user-safe message; never includes the API key."""


class LLM(Protocol):
    model: str

    def complete(self, system: str, messages: list[dict]) -> str: ...


def _detail(e: Exception, secret: str = "") -> str:
    """Extract the provider's own explanation from an API error (key redacted)."""
    body = getattr(e, "body", None)
    msg = None
    if isinstance(body, dict):
        err = body.get("error", body.get("message"))
        msg = err.get("message") if isinstance(err, dict) else err
    msg = msg or getattr(e, "message", None) or str(e)
    msg = " ".join(str(msg).split())
    if secret:
        msg = msg.replace(secret, "[redacted]")
    return msg[:300]


class LLMClient:
    def __init__(self, api_key: str, model: str, base_url: str,
                 timeout: float = 60.0, max_retries: int = 2):
        if not api_key:
            raise LLMError("LLM_API_KEY is not set in the backend .env file.")
        if not model:
            raise LLMError("LLM_MODEL is not set in the backend .env file.")
        from openai import OpenAI

        self.model = model
        self.host = urlparse(base_url).netloc or base_url
        self._key = api_key
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

    def _call(self, system: str, messages: list[dict], temperature: float | None):
        kwargs = dict(model=self.model, messages=[{"role": "system", "content": system}, *messages])
        if temperature is not None:
            kwargs["temperature"] = temperature
        return self._client.chat.completions.create(**kwargs)

    def complete(self, system: str, messages: list[dict], temperature: float = 0.2) -> str:
        import openai

        who = self.host
        try:
            try:
                r = self._call(system, messages, temperature)
            except openai.BadRequestError as e:
                # Some models reject sampling parameters; retry once without temperature.
                if "temperature" in _detail(e, self._key).lower():
                    r = self._call(system, messages, None)
                else:
                    raise
        except openai.AuthenticationError as e:
            raise LLMError(f"{who} rejected the API key (401). Check LLM_API_KEY.") from e
        except openai.PermissionDeniedError as e:
            raise LLMError(f"{who} denied access (403): {_detail(e, self._key)}") from e
        except openai.NotFoundError as e:
            raise LLMError(f"Model '{self.model}' not found on {who} (check LLM_MODEL). "
                           f"Provider said: {_detail(e, self._key)}") from e
        except openai.RateLimitError as e:
            raise LLMError(f"{who} rate limit or quota reached (429). Try again shortly.") from e
        except openai.BadRequestError as e:
            raise LLMError(f"{who} rejected the request (400): {_detail(e, self._key)} "
                           f"[model='{self.model}']. If it mentions the model or key, fix LLM_MODEL / "
                           f"LLM_API_KEY / LLM_BASE_URL in .env.") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise LLMError(f"Could not reach {who} (timeout/network). Try again.") from e
        except openai.APIStatusError as e:
            raise LLMError(f"{who} returned an error (HTTP {e.status_code}): {_detail(e, self._key)}") from e
        content = r.choices[0].message.content if r.choices else None
        if not content:
            raise LLMError(f"{who} returned an empty response.")
        return content
