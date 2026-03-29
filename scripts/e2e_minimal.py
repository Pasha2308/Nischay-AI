"""Single-URL quick pipeline check (unbuffered prints)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.orchestrator import Orchestrator
from shared.models.config import CrawlConfig, FrameworkConfig


async def main() -> None:
    print("start", flush=True)
    cfg = FrameworkConfig(
        target_url="https://example.com",
        crawl=CrawlConfig(target_url="https://example.com", max_pages=1, max_depth=1),
        scan_mode="fast",
        capture_video="off",
    )
    o = Orchestrator(cfg)
    r = await asyncio.wait_for(o._run_pipeline(), timeout=180)
    print("risk", r.get("risk_score"), "retries", (r.get("pipeline_metrics") or {}).get("step_retries"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
