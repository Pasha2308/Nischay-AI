#!/usr/bin/env python3
"""
End-to-end scan smoke test against a few real sites (no HTTP server).

Logs per site: pipeline_metrics (total_scan_time, crawl_time, execution_time, retries_count),
risk_score, executive summary (Groq if configured). If total_scan_time > 120s, logs stage
breakdown (crawl vs execution vs other: browser/auth/plan/coverage/report).

Usage (from repo root):
  python scripts/e2e_scan_smoke.py

Env:
  LLM_API_KEY, LLM_BASE_URL, LLM_MODEL — optional; executive summary uses LLMClient when set.
  SCAN_PIPELINE_TIMEOUT_SECONDS — optional; mirrors API default 180s for local runs.
  E2E_URLS — comma-separated URLs (default: three small public pages).
  E2E_MAX_SCAN_SECONDS — per-scan wall time limit for pass/fail (default 120; goal <120s).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.orchestrator import Orchestrator
from backend.services.llm_client import LLMClient, _is_placeholder_api_key
from shared.models.config import CrawlConfig, FrameworkConfig

SLOW_THRESHOLD_S = 120.0


def _default_sites() -> list[str]:
    raw = (os.environ.get("E2E_URLS") or "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return [
        "https://example.com",
        "https://httpbin.org/html",
        "https://www.iana.org/help/example-domains",
    ]


def _log_metrics_and_breakdown(pm: dict) -> None:
    """Log the four pipeline counters; if total_scan_time > threshold, log slowest stage."""
    total = pm.get("total_scan_time")
    crawl = pm.get("crawl_time")
    exec_t = pm.get("execution_time")
    retries = int(pm.get("retries_count") or pm.get("step_retries") or 0)
    print(
        f"  metrics: total_scan_time={total}s crawl_time={crawl} "
        f"execution_time={exec_t} retries_count={retries}",
        flush=True,
    )
    if total is None:
        return
    try:
        t = float(total)
    except (TypeError, ValueError):
        return
    if t <= SLOW_THRESHOLD_S:
        return
    # Crawl + execution are measured; remainder is browser launch, auth, plan, coverage, report, etc.
    c = float(crawl) if crawl is not None else None
    e = float(exec_t) if exec_t is not None else None
    if c is not None and e is not None:
        other = max(0.0, round(t - c - e, 2))
        parts = [("crawl", c), ("execution", e), ("other_overhead", other)]
    elif c is not None:
        parts = [("crawl", c), ("execution", 0.0), ("other_overhead", max(0.0, round(t - c, 2)))]
    elif e is not None:
        parts = [("crawl", 0.0), ("execution", e), ("other_overhead", max(0.0, round(t - e, 2)))]
    else:
        parts = [("unknown_breakdown", t)]
    slowest = max(parts, key=lambda x: x[1])
    print(
        f"  SLOW (total_scan_time > {SLOW_THRESHOLD_S}s): slowest_stage={slowest[0]} ({slowest[1]}s)",
        flush=True,
    )
    detail = " ".join(f"{name}={val}s" for name, val in sorted(parts, key=lambda x: -x[1]))
    print(f"  breakdown: {detail}", flush=True)
    print(
        "  (other_overhead = browser/auth/plan/coverage/report vs wall clock not in crawl+execute)",
        flush=True,
    )


def _llm_ok() -> bool:
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    return bool(key) and not _is_placeholder_api_key(key)


async def _executive_summary_like_api(result: dict, target_url: str = "") -> str:
    """Mirror api.server._generate_executive_summary fallback / LLM path."""
    from api.server import (
        _build_executive_summary_user_prompt,
        _executive_summary_system_prompt,
        _fallback_executive_summary,
        _normalize_scan_task,
        _resolve_pages_scanned,
        _summary_target_url,
    )

    issues = list(result.get("issues") or [])
    url = _summary_target_url(result, target_url)
    if _resolve_pages_scanned(result) == 0:
        return ""
    if not _llm_ok():
        return _fallback_executive_summary(result, issues, url)
    try:
        llm = LLMClient()
        st = _normalize_scan_task(str(result.get("scan_task") or "full_app"))
        user_prompt = _build_executive_summary_user_prompt(result, url, scan_task=st)
        summary = await llm.complete(
            system_prompt=_executive_summary_system_prompt(st),
            user_prompt=user_prompt,
        )
        return (summary or "").strip() or _fallback_executive_summary(result, issues, url)
    except Exception as e:
        return f"[LLM error: {e}]"


async def run_one(url: str, max_pages: int = 1) -> dict:
    cfg = FrameworkConfig(
        target_url=url,
        crawl=CrawlConfig(target_url=url, max_pages=max_pages, max_depth=1),
        scan_mode="fast",
        capture_video="off",
    )
    orch = Orchestrator(cfg)
    t0 = time.perf_counter()
    out = await orch._run_pipeline()
    elapsed = time.perf_counter() - t0
    metrics = out.get("pipeline_metrics") or {}
    _log_metrics_and_breakdown(metrics)
    retries = int(metrics.get("retries_count") or metrics.get("step_retries") or 0)
    risk = out.get("risk_score")
    print(f"  wall_clock_s={elapsed:.1f} risk_score={risk!r}", flush=True)
    summary = await _executive_summary_like_api(out, url)
    print(
        f"  executive_summary ({len(summary)} chars): {summary[:280]}{'...' if len(summary) > 280 else ''}",
        flush=True,
    )
    return {
        "url": url,
        "elapsed_s": elapsed,
        "total_scan_time": metrics.get("total_scan_time"),
        "crawl_time": metrics.get("crawl_time"),
        "execution_time": metrics.get("execution_time"),
        "retries_count": retries,
        "risk_score": risk,
        "summary_ok": bool(summary and len(summary) > 20),
    }


async def main() -> int:
    print("E2E scan smoke test", flush=True)
    sites = _default_sites()
    print("  sites:", sites, flush=True)
    print("  LLM configured for Groq-style summary:", _llm_ok(), flush=True)
    results = []
    for url in sites:
        print(f"\n--- {url} ---", flush=True)
        try:
            row = await run_one(url)
            results.append(row)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            import traceback

            traceback.print_exc()
            results.append({"url": url, "error": str(e)})

    print("\n=== SUMMARY ===", flush=True)
    for r in results:
        print(r, flush=True)
    wall_vals = [
        float(r["elapsed_s"])
        for r in results
        if isinstance(r.get("elapsed_s"), (int, float))
    ]
    total_vals = [
        float(r["total_scan_time"])
        for r in results
        if isinstance(r.get("total_scan_time"), (int, float))
    ]
    max_wall = max(wall_vals) if wall_vals else 0.0
    max_total = max(total_vals) if total_vals else None
    print(
        f"max_wall_clock_s={max_wall:.1f} max_total_scan_time_s={max_total} "
        f"(goal: total_scan_time < {SLOW_THRESHOLD_S}s consistently)",
        flush=True,
    )
    failed = [r for r in results if r.get("error")]
    if failed:
        print("FAILURES:", failed, flush=True)
        return 1
    limit = float((os.environ.get("E2E_MAX_SCAN_SECONDS") or "120").strip() or "120")
    slow = [
        r
        for r in results
        if isinstance(r.get("total_scan_time"), (int, float)) and float(r["total_scan_time"]) > limit
    ]
    if slow:
        print(f"FAIL: total_scan_time exceeded {limit}s:", slow, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
