"""LLMClient error mapping, tested with a fake `openai` module (no network, no SDK needed)."""
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fake_openai(behaviour):
    m = types.ModuleType("openai")

    class APIStatusError(Exception):
        def __init__(self, msg, status=400, body=None):
            super().__init__(msg); self.message, self.status_code, self.body = msg, status, body

    class BadRequestError(APIStatusError): pass
    class AuthenticationError(APIStatusError): pass
    class PermissionDeniedError(APIStatusError): pass
    class NotFoundError(APIStatusError): pass
    class RateLimitError(APIStatusError): pass
    class APITimeoutError(Exception): pass
    class APIConnectionError(Exception): pass

    class _Completions:
        calls = []
        def create(self, **kw):
            _Completions.calls.append(kw)
            return behaviour(kw, m)

    class OpenAI:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=_Completions())

    for c in (APIStatusError, BadRequestError, AuthenticationError, PermissionDeniedError, NotFoundError,
              RateLimitError, APITimeoutError, APIConnectionError, OpenAI):
        setattr(m, c.__name__, c)
    m._calls = _Completions.calls
    return m


def ok_response(text="hi"):
    msg = types.SimpleNamespace(content=text)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


class LLMClientTests(unittest.TestCase):
    def run_client(self, behaviour):
        fake = fake_openai(behaviour)
        old = sys.modules.get("openai")
        sys.modules["openai"] = fake
        try:
            from app.rag.llm_client import LLMClient
            return LLMClient("sk-secret-123", "grok-x", "https://api.groq.com/openai/v1"), fake
        finally:
            self._restore = (old,)

    def tearDown(self):
        old = getattr(self, "_restore", (None,))[0]
        if old is None: sys.modules.pop("openai", None)
        else: sys.modules["openai"] = old

    def test_success(self):
        c, _ = self.run_client(lambda kw, m: ok_response("answer"))
        self.assertEqual(c.complete("sys", [{"role": "user", "content": "q"}]), "answer")

    def test_400_surfaces_xai_reason_and_redacts_key(self):
        def b(kw, m):
            raise m.BadRequestError("bad", 400, {"code": "x", "error": "The model grok-x does not exist sk-secret-123"})
        c, _ = self.run_client(b)
        from app.rag.llm_client import LLMError
        with self.assertRaises(LLMError) as cm:
            c.complete("s", [{"role": "user", "content": "q"}])
        text = str(cm.exception)
        self.assertIn("does not exist", text); self.assertIn("grok-x", text); self.assertIn("api.groq.com", text)
        self.assertNotIn("sk-secret-123", text)

    def test_temperature_rejected_retries_without_it(self):
        def b(kw, m):
            if "temperature" in kw:
                raise m.BadRequestError("x", 400, {"error": "Argument not supported: temperature"})
            return ok_response("fine")
        c, fake = self.run_client(b)
        self.assertEqual(c.complete("s", [{"role": "user", "content": "q"}]), "fine")
        self.assertEqual(len(fake._calls), 2); self.assertNotIn("temperature", fake._calls[1])

    def test_other_errors_mapped(self):
        from app.rag.llm_client import LLMError
        for exc_name, status, needle in [("AuthenticationError", 401, "401"), ("NotFoundError", 404, "not found"),
                                         ("RateLimitError", 429, "429"), ("PermissionDeniedError", 403, "403")]:
            def b(kw, m, n=exc_name, s=status):
                raise getattr(m, n)("x", s, {"error": "why"})
            c, _ = self.run_client(b)
            with self.assertRaises(LLMError) as cm:
                c.complete("s", [{"role": "user", "content": "q"}])
            self.assertIn(needle, str(cm.exception).lower())

    def test_missing_key_or_model(self):
        from app.rag.llm_client import LLMClient, LLMError
        sys.modules["openai"] = fake_openai(lambda kw, m: ok_response())
        with self.assertRaises(LLMError): LLMClient("", "m", "https://x/v1")
        with self.assertRaises(LLMError): LLMClient("k", "", "https://x/v1")



class ConfigTests(unittest.TestCase):
    def env(self, **e):
        import os
        from unittest import mock
        from app import config
        with mock.patch.object(config, "_load_dotenv", lambda: None), mock.patch.dict(os.environ, e, clear=True):
            return config.Settings.from_env()

    def test_groq_is_default(self):
        s = self.env(LLM_API_KEY="k", LLM_MODEL="openai/gpt-oss-120b")
        self.assertEqual(s.llm_base_url, "https://api.groq.com/openai/v1")
        self.assertEqual((s.llm_api_key, s.llm_model), ("k", "openai/gpt-oss-120b"))

    def test_groq_named_variables(self):
        s = self.env(GROQ_API_KEY="g", GROQ_MODEL="m")
        self.assertEqual((s.llm_api_key, s.llm_model), ("g", "m"))

    def test_custom_base_url(self):
        self.assertEqual(self.env(LLM_API_KEY="k", LLM_MODEL="m", LLM_BASE_URL="https://api.openai.com/v1").llm_base_url,
                         "https://api.openai.com/v1")

    def test_legacy_xai_config_still_points_at_xai(self):
        s = self.env(XAI_API_KEY="x", GROK_MODEL="grok-m")
        self.assertEqual((s.llm_api_key, s.llm_model, s.llm_base_url), ("x", "grok-m", "https://api.x.ai/v1"))

    def test_old_variable_names_holding_a_groq_key_go_to_groq(self):
        s = self.env(XAI_API_KEY="gsk_abc", GROK_MODEL="openai/gpt-oss-120b")
        self.assertEqual(s.llm_base_url, "https://api.groq.com/openai/v1")
        self.assertEqual(s.llm_model, "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()
