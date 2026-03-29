"""OpenAI-compatible chat client for Groq and similar providers."""

from __future__ import annotations

import logging
import os

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

logger = logging.getLogger(__name__)


def _is_placeholder_api_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return True
    if k == "YOUR_GROQ_API_KEY":
        return True
    # Common .env template values
    if k.startswith("YOUR_"):
        return True
    return False


class LLMClient:
    """Async HTTP client for `/v1/chat/completions` style APIs."""

    def __init__(self) -> None:
        self.provider = (os.environ.get("LLM_PROVIDER") or "").strip()
        self.api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        self.model_smart = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.model_fast = os.getenv("LLM_MODEL_FAST", "llama-3.1-8b-instant")
        # Backward compat: callers/tests use ``llm.model`` for the primary (smart) model id
        self.model = self.model_smart
        base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
        self.base_url = base
        if (
            self.api_key
            and self.model_smart
            and self.base_url
            and not _is_placeholder_api_key(self.api_key)
        ):
            logger.debug(
                "LLMClient configured: model_smart=%s model_fast=%s base_url=%s key_prefix=%s",
                self.model_smart,
                self.model_fast,
                self.base_url,
                (self.api_key[:5] + "...") if len(self.api_key) > 5 else "(short)",
            )
        elif self.api_key and _is_placeholder_api_key(self.api_key):
            logger.warning(
                "LLM_API_KEY appears to be a placeholder; set a real key in .env for LLM calls."
            )

    async def verify_models(self) -> None:
        """GET /v1/models and confirm ``model_smart`` / ``model_fast`` ids exist (Groq/OpenAI-style API)."""
        if not self.api_key or _is_placeholder_api_key(self.api_key) or not self.base_url:
            return
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            models = [m["id"] for m in data["data"]]
        except Exception as e:
            print(f"WARNING: Could not list models: {e}", flush=True)
            logger.warning("verify_models failed: %s", e)
            return

        for m in [self.model_smart, self.model_fast]:
            if m not in models:
                print(f"WARNING: Model {m} not available", flush=True)
            else:
                print(f"Model {m} OK", flush=True)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        fast: bool = False,
        json_mode: bool = False,
    ) -> str:
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set")
        if _is_placeholder_api_key(self.api_key):
            raise ValueError(
                "LLM_API_KEY is a placeholder or invalid; replace it in .env with your real API key."
            )
        model = self.model_fast if fast else self.model_smart
        if not model:
            raise ValueError("LLM model id is empty (check LLM_MODEL / LLM_MODEL_FAST)")
        if not self.base_url:
            raise ValueError("LLM_BASE_URL is not set")

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            if os.getenv("DEBUG_LLM") == "1":
                print("LLM RAW RESPONSE:", response.text, flush=True)
            response.raise_for_status()
            data = response.json()

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Unexpected LLM response shape: {data!r}") from e
