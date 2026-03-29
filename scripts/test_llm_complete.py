#!/usr/bin/env python3
"""Manual LLM smoke: loads .env via LLMClient, calls complete(), prints result."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def main() -> int:
    from backend.services.llm_client import LLMClient

    key = (os.getenv("LLM_API_KEY") or "").strip()
    print("LLM CONFIG:", key[:5] if key else "NOT SET", flush=True)
    print("LLM_BASE_URL:", (os.getenv("LLM_BASE_URL") or "NOT SET")[:80], flush=True)
    print("LLM_MODEL:", os.getenv("LLM_MODEL") or "NOT SET", flush=True)

    llm = LLMClient()
    _kp = llm.api_key[:5] + "..." if len(llm.api_key) > 5 else llm.api_key
    print(
        "LLMClient instance:",
        f"key_prefix={_kp!r}",
        f"model={llm.model!r}",
        f"base_url={llm.base_url!r}",
        flush=True,
    )

    try:
        out = await llm.complete(
            "You are a test assistant.",
            'Reply with exactly one word: "ok"',
        )
        print("llm.complete() output:", out[:500], flush=True)
        return 0
    except Exception as e:
        print("llm.complete() FAILED:", e, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
