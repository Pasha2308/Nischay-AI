"""Run the full Nischay AI ecommerce scan locally (headed browser) + CTO report."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

from playwright.async_api import async_playwright

from backend.core.ecommerce_plan import expand_selected_flows, run_ecommerce_scan
from backend.services.report_builder import build_cto_report

logger = logging.getLogger(__name__)

FLOWS = expand_selected_flows(["full_app_scan"])


def _login_mode_from_messages(messages: list[str]) -> str:
    blob = "\n".join(messages)
    if "Login successful — starting scan" in blob:
        return "PROGRAMMATIC"
    if "Login detected — resuming scan" in blob:
        return "HUMAN"
    return "UNKNOWN"


def _print_test_summary(
    *,
    test_label: str,
    total_time_s: float,
    login_success: bool | None,
    login_mode: str,
    flows_executed: list[str],
    timeout_logs: list[str],
    defect_count: int,
) -> None:
    print("", flush=True)
    print(f"=== {test_label} SUMMARY ===", flush=True)
    print(f"Total time: {total_time_s:.2f}s", flush=True)
    print(f"Login success: {login_success}", flush=True)
    print(f"LOGIN MODE USED: {login_mode}", flush=True)
    print(f"Flows executed: {flows_executed}", flush=True)
    print(f"Timeout logs ({len(timeout_logs)}):", flush=True)
    for line in timeout_logs:
        print(f"  {line}", flush=True)
    print(f"Number of defects: {defect_count}", flush=True)


async def _run_single_site(
    *,
    site_url: str,
    site_credentials: dict[str, Any],
    context: Any,
) -> tuple[dict[str, Any], list[str], float]:
    """Returns (scan_result, captured_messages, duration_seconds)."""
    creds: dict[str, Any] = {
        **site_credentials,
        "target_url": site_url,
        "browse_start_url": site_url,
    }
    messages: list[str] = []

    async def emit_event(msg: str) -> None:
        messages.append(msg)
        print(msg, flush=True)

    page = await context.new_page()
    started = time.perf_counter()
    result: dict[str, Any] = {}
    try:
        logger.info("Navigating to %s", site_url)
        await page.goto(site_url, wait_until="domcontentloaded", timeout=90_000)
        logger.info("Running ecommerce flows: %s", FLOWS)
        result = await run_ecommerce_scan(page, FLOWS, creds, emit_event)
    finally:
        await page.close()

    duration_seconds = time.perf_counter() - started
    return result, messages, duration_seconds


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    logger.info("Starting headed browser (chromium, visible window)")

    grand_t0 = time.perf_counter()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # TEST 1 — demo site (predictable flows)
        url = "https://automationexercise.com"
        credentials = {
            "username": "pashapasha8138@gmail.com",
            "password": "pasha@23aug",
        }
        result1, messages1, dur1 = await _run_single_site(
            site_url=url,
            site_credentials=credentials,
            context=context,
        )
        actions1 = result1.get("actions") or []
        login_ok_1: bool | None = None
        for a in actions1:
            if a.get("flow") == "auth" and a.get("step") == "valid_login":
                login_ok_1 = bool(a.get("success"))
                break
        mode1 = _login_mode_from_messages(messages1)
        timeouts1 = [
            m
            for m in messages1
            if ("⏱" in m) or ("timeout" in m.lower()) or ("timed out" in m.lower())
        ]
        metrics1 = result1.get("metrics") or {}
        flows_done_1 = list(metrics1.keys())

        _print_test_summary(
            test_label="TEST 1",
            total_time_s=dur1,
            login_success=login_ok_1,
            login_mode=mode1,
            flows_executed=flows_done_1,
            timeout_logs=timeouts1,
            defect_count=len(result1.get("defects") or []),
        )

        # TEST 2 — same demo site (swap URL here for multi-site regression)
        url = "https://automationexercise.com"
        credentials = {
            "username": "pashapasha8138@gmail.com",
            "password": "pasha@23aug",
        }
        result2, messages2, dur2 = await _run_single_site(
            site_url=url,
            site_credentials=credentials,
            context=context,
        )
        actions2 = result2.get("actions") or []
        login_ok_2: bool | None = None
        for a in actions2:
            if a.get("flow") == "auth" and a.get("step") == "valid_login":
                login_ok_2 = bool(a.get("success"))
                break
        mode2 = _login_mode_from_messages(messages2)
        timeouts2 = [
            m
            for m in messages2
            if ("⏱" in m) or ("timeout" in m.lower()) or ("timed out" in m.lower())
        ]
        metrics2 = result2.get("metrics") or {}
        flows_done_2 = list(metrics2.keys())

        _print_test_summary(
            test_label="TEST 2",
            total_time_s=dur2,
            login_success=login_ok_2,
            login_mode=mode2,
            flows_executed=flows_done_2,
            timeout_logs=timeouts2,
            defect_count=len(result2.get("defects") or []),
        )

        grand_total = time.perf_counter() - grand_t0
        print("", flush=True)
        print("=== BOTH TESTS (SEQUENTIAL) ===", flush=True)
        print(f"Total time (both tests + browser): {grand_total:.2f}s", flush=True)

        # Optional: CTO report for TEST 2 last result (keeps previous behavior partially)
        try:
            report = await build_cto_report(
                {
                    "target_url": url,
                    "defects": result2.get("defects") or [],
                    "flows": [],
                    "action_trail": result2.get("actions") or [],
                    "duration_seconds": dur2,
                    "metrics": result2.get("metrics") or {},
                    "task_results": result2.get("task_results") or [],
                }
            )
        except Exception:
            logger.exception("build_cto_report failed")
            raise

        print("\n=== FINAL REPORT (TEST 2) ===", flush=True)
        print(json.dumps(report, indent=2, default=str), flush=True)

        await context.close()
        await browser.close()
        logger.info("Browser closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr, flush=True)
        sys.exit(130)
    except Exception:
        logging.exception("run_scan aborted with error")
        sys.exit(1)
