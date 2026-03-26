"""Minimal AI client abstraction used by planner/executor/reporter.

This keeps the pipeline runnable even without any AI provider configured.
If no provider credentials are available, the constructor raises EnvironmentError
and callers are expected to fall back to non-AI logic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_DEBUG_DIR: Path | None = None


def set_debug_dir(path: Path) -> None:
    global _DEBUG_DIR
    _DEBUG_DIR = path
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)


class AIClient:
    def __init__(
        self,
        provider: str = "anthropic",
        model: str = "",
        base_url: str | None = None,
        max_tokens: int | None = None,
    ):
        self.provider = (provider or "").lower().strip()
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens

        # Conservative availability checks: if not configured, signal fallback.
        if self.provider == "anthropic":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise EnvironmentError("ANTHROPIC_API_KEY is not set")
        elif self.provider == "ollama":
            # Ollama typically runs locally; allow without env.
            pass
        else:
            raise EnvironmentError(f"Unsupported ai_provider '{provider}'")

    def complete(self, system_prompt: str, user_message: str, max_tokens: int = 500) -> str:
        raise RuntimeError(
            "AI provider integration not implemented in this repo. "
            "Set ai_provider to 'ollama' and implement shared/utils/ai/client.py, "
            "or run in fallback mode (no AI)."
        )

    def complete_json(self, system_prompt: str, user_message: str, max_tokens: int = 1000) -> dict[str, Any]:
        text = self.complete(system_prompt=system_prompt, user_message=user_message, max_tokens=max_tokens)
        return self._parse_json_response(text)

    def complete_with_image(
        self,
        system_prompt: str,
        user_message: str,
        image_base64: str,
        max_tokens: int = 500,
    ) -> str:
        # Placeholder: keep interface stable.
        return self.complete(system_prompt=system_prompt, user_message=user_message, max_tokens=max_tokens)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from a model response, tolerating markdown fences."""
        if not text:
            return {}
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()
        try:
            return json.loads(raw)
        except Exception:
            # As a last resort, find the first {...} block.
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise

