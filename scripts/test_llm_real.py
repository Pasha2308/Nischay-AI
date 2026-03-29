#!/usr/bin/env python3
"""Verify LLM integration returns real model text (requires valid .env)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 1. Load .env from project root
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")


async def main() -> None:
    from backend.services.llm_client import LLMClient

    llm = LLMClient()

    try:
        response = await llm.complete(
            system_prompt="You are a senior QA risk analyst",
            user_prompt="Summarize: checkout button fails on payment page causing revenue loss",
        )
    except Exception as e:
        print(f"ERROR: LLM call failed: {e}", file=sys.stderr, flush=True)
        raise SystemExit(1) from e

    text = (response or "").strip()
    print(response, flush=True)

    if not text:
        print("ERROR: response is empty", file=sys.stderr, flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
