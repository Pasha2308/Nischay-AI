"""
Nischay AI — full system diagnostic (two real e-commerce sites).

Does NOT modify core modules; orchestrates handle_login + run_ecommerce_scan only.
Run: python -m backend.run_system_diagnostic
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright

from backend.core.login_handler import handle_login
from backend.core.ecommerce_plan import expand_selected_flows, run_ecommerce_scan

logger = logging.getLogger(__name__)

FLOWS = expand_selected_flows(["full_app_scan"])

FLOW_TIMEOUTS = {
    "auth": 25,
    "browse": 15,
    "cart": 20,
    "checkout": 15,
    "support": 10,
    "ui": 10,
}

# Demo / investor default (no region gate; predictable add-to-cart)
DEMO_URL = "https://automationexercise.com"

# TEST 1
url = DEMO_URL
credentials = {
    "username": "pashapasha8138@gmail.com",
    "password": "pasha@23aug",
}

# TEST 2 (same site for now — lock demo; swap for regression on hard sites later)
url_2 = DEMO_URL
credentials_2 = {
    "username": "pashapasha8138@gmail.com",
    "password": "pasha@23aug",
}


@dataclass
class TimedCapture:
    """Monotonic timestamps for every emitted line."""

    entries: list[tuple[float, str]] = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)

    def log(self, msg: str) -> None:
        self.entries.append((time.perf_counter() - self.t0, msg))
        print(msg, flush=True)

    def messages(self) -> list[str]:
        return [m for _, m in self.entries]


def _login_mode_label(messages: list[str]) -> str:
    blob = "\n".join(messages)
    if "Login successful — starting scan" in blob:
        return "PROGRAMMATIC"
    if "Login detected — resuming scan" in blob:
        return "HUMAN"
    if "Login timeout — continuing without login" in blob or "Could not load login page" in blob:
        return "FAILED"
    return "UNKNOWN"


def _messages_for_handle_login_block(entries: list[tuple[float, str]]) -> list[str]:
    out: list[str] = []
    inside = False
    for _t, m in entries:
        if "handle_login() START" in m:
            inside = True
            continue
        if "handle_login() END" in m:
            break
        if inside:
            out.append(m)
    return out


async def _post_login_signals(page: Any, url_at_human_start: str) -> dict[str, bool]:
    """Signals aligned with login_handler heuristics (observation only)."""
    out: dict[str, bool] = {}
    try:
        cur = page.url or ""
        out["url_changed_vs_human_start"] = bool(cur.strip() and cur != url_at_human_start)
    except Exception:
        out["url_changed_vs_human_start"] = False
    try:
        pwd = await page.query_selector("input[type='password']")
        out["password_field_gone"] = pwd is None
    except Exception:
        out["password_field_gone"] = False
    try:
        ctx = page.context
        cookies = await ctx.cookies()
        out["cookies_nonzero"] = len(cookies) > 0
        out["cookie_count"] = len(cookies)
    except Exception:
        out["cookies_nonzero"] = False
        out["cookie_count"] = 0
    try:
        nav = await page.query_selector(
            "a:has-text('Logout'), a:has-text('Account'), a:has-text('Sign out')"
        )
        out["account_or_logout_found"] = nav is not None
    except Exception:
        out["account_or_logout_found"] = False
    return out


def _parse_flow_boundaries(entries: list[tuple[float, str]]) -> dict[str, tuple[float, float | None]]:
    """Start/end seconds (relative to capture t0) per flow key."""
    bounds: dict[str, tuple[float, float | None]] = {}
    re_start = re.compile(r"Starting\s+(\w+)\s+flow")
    re_done = re.compile(r"✅\s+(\w+)\s+complete")
    re_fail = re.compile(r"❌\s+(\w+)\s+failed")
    for t, msg in entries:
        m = re_start.search(msg)
        if m:
            fk = m.group(1).lower()
            bounds[fk] = (t, None)
            continue
        m = re_done.search(msg) or re_fail.search(msg)
        if m:
            fk = m.group(1).lower()
            if fk in bounds:
                s, _ = bounds[fk]
                bounds[fk] = (s, t)
    return bounds


def _actions_for_flow(actions: list[dict[str, Any]], flow: str) -> list[dict[str, Any]]:
    return [a for a in actions if isinstance(a, dict) and a.get("flow") == flow]


def _defects_for_flow(defects: list[dict[str, Any]], flow: str) -> list[dict[str, Any]]:
    out = []
    seen: set[int] = set()
    for d in defects:
        if not isinstance(d, dict):
            continue
        i = id(d)
        if i in seen:
            continue
        fl = str(d.get("defect") or "")
        if d.get("flow") == flow:
            out.append(d)
            seen.add(i)
        elif flow == "auth" and fl in ("login_failure", "login_not_persisted"):
            out.append(d)
            seen.add(i)
    return out


def _scan_login_not_persisted(defects: list[dict[str, Any]]) -> bool:
    for d in defects:
        if isinstance(d, dict) and d.get("defect") == "login_not_persisted":
            return True
    return False


def _false_positive_cookie_heuristic(
    cookies_before_login: int,
    login_messages: list[str],
    timed: list[tuple[float, str]],
    login_start_offset: float,
) -> bool:
    """
    Flag if cookies already existed before login and success appeared very early in human wait,
    suggesting cookie-based false positive in core wait loop.
    """
    if cookies_before_login <= 0:
        return False
    blob = "\n".join(login_messages)
    if "Login successful — starting scan" in blob:
        return False
    if "Login detected — resuming scan" not in blob:
        return False
    human_start = None
    for t, m in timed:
        if "Please log in manually" in m or "Waiting up to 3 minutes" in m:
            human_start = t
            break
    first_detect = None
    if human_start is not None:
        for t, m in timed:
            if t <= human_start:
                continue
            if "Login detected — resuming scan" in m:
                first_detect = t
                break
    if human_start is None or first_detect is None:
        return False
    if (first_detect - human_start) < 2.0 and cookies_before_login >= 1:
        return True
    return False


def _verdict(
    login_ok: bool,
    flow_pass: dict[str, bool],
    total_defects: int,
    total_actions: int,
    scan_s: float,
) -> str:
    failed_flows = sum(1 for v in flow_pass.values() if not v)
    if not login_ok and failed_flows >= 4:
        return "BROKEN"
    if failed_flows == 0 and login_ok and total_actions > 5:
        return "WORKING"
    if failed_flows <= 2 and (total_defects > 0 or total_actions > 3):
        return "PARTIALLY WORKING"
    if scan_s > 120 and total_actions < 5:
        return "BROKEN"
    return "PARTIALLY WORKING"


def _major_issues(
    site: str,
    login_ok: bool,
    login_mode: str,
    metrics: dict[str, Any],
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    false_positive: bool,
) -> list[str]:
    issues: list[str] = []
    if not login_ok:
        issues.append(f"[{site}] Login did not complete successfully (mode={login_mode}).")
    if false_positive:
        issues.append(f"[{site}] Possible false-positive login detection (cookies present before human step).")
    for fk, fm in (metrics or {}).items():
        if isinstance(fm, dict) and fm.get("timed_out"):
            issues.append(f"[{site}] Flow {fk} timed out (run_flow_with_timeout).")
        if isinstance(fm, dict) and fm.get("error"):
            issues.append(f"[{site}] Flow {fk} error: {str(fm.get('error'))[:120]}")
    if _scan_login_not_persisted(defects):
        issues.append(f"[{site}] login_not_persisted defect recorded after auth reload.")
    cart_m = metrics.get("cart") if isinstance(metrics, dict) else {}
    if isinstance(cart_m, dict) and cart_m.get("cart_skipped_requires_login"):
        issues.append(f"[{site}] Cart flow skipped: requires login / no session UI.")
    if len(defects) == 0 and len(actions) < 8:
        issues.append(f"[{site}] Very few actions and zero defects — possible shallow execution.")
    return issues[:5]


def _flow_passed(
    flow: str,
    flow_metrics: dict[str, Any],
    flow_actions: list[dict[str, Any]],
    flow_defects: list[dict[str, Any]],
) -> bool:
    if isinstance(flow_metrics, dict) and flow_metrics.get("timed_out"):
        return False
    if isinstance(flow_metrics, dict) and flow_metrics.get("error") and not flow_actions:
        return False
    if flow == "cart" and flow_metrics.get("cart_skipped_requires_login"):
        return False
    return len(flow_actions) > 0 or len(flow_defects) > 0


async def _run_one_test(
    *,
    label: str,
    site_url: str,
    site_creds: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    cap = TimedCapture()
    creds_full: dict[str, Any] = {
        **site_creds,
        "target_url": site_url,
        "browse_start_url": site_url,
        "login_url": site_url,
    }

    page = await context.new_page()
    t_login_wall = 0.0
    login_ok = False
    fp = False
    mode = "UNKNOWN"
    cookies_before = 0
    url_before = ""
    signals_after: dict[str, Any] = {}
    scan_result: dict[str, Any] = {}
    scan_started = 0.0
    scan_ended = 0.0

    try:
        cap.log(f"[{label}] Navigating to {site_url}")
        await page.goto(site_url, wait_until="domcontentloaded", timeout=90_000)
        url_before = page.url
        try:
            cookies_before = len(await context.cookies())
        except Exception as e:
            cap.log(f"[{label}] WARN: could not read cookies before login: {e!s}")

        cap.log(f"[{label}] Cookies count before handle_login: {cookies_before}")
        cap.log(f"[{label}] === handle_login() START ===")

        t_login = time.perf_counter()

        async def emit_login(msg: str) -> None:
            cap.log(msg)

        login_ok = await handle_login(page, creds_full, emit_login)
        t_login_wall = time.perf_counter() - t_login

        cap.log(f"[{label}] === handle_login() END === success={login_ok} wall_s={t_login_wall:.2f}")

        mode = _login_mode_label(_messages_for_handle_login_block(cap.entries))
        if not login_ok and mode == "UNKNOWN":
            mode = "FAILED"

        url_human_anchor = url_before
        signals_after = await _post_login_signals(page, url_human_anchor)

        cap.log(f"[{label}] --- POST-LOGIN SIGNAL SNAPSHOT (observation) ---")
        cap.log(
            f"[{label}]   URL changed vs page load: {signals_after.get('url_changed_vs_human_start')}"
        )
        cap.log(f"[{label}]   Password field gone: {signals_after.get('password_field_gone')}")
        cap.log(
            f"[{label}]   Cookies non-zero: {signals_after.get('cookies_nonzero')} "
            f"(count={signals_after.get('cookie_count')})"
        )
        cap.log(
            f"[{label}]   Account/logout link: {signals_after.get('account_or_logout_found')}"
        )
        cap.log(
            f"[{label}] Detection signals (which may have matched in core — end-state snapshot): "
            f"URL={signals_after.get('url_changed_vs_human_start')}, "
            f"PWD_GONE={signals_after.get('password_field_gone')}, "
            f"COOKIES={signals_after.get('cookies_nonzero')}, "
            f"NAV={signals_after.get('account_or_logout_found')}"
        )

        fp = _false_positive_cookie_heuristic(
            cookies_before,
            cap.messages(),
            [(t, m) for t, m in cap.entries],
            0.0,
        )
        if fp:
            cap.log("⚠️ FALSE POSITIVE LOGIN DETECTION (heuristic: cookies before login + rapid 'Login detected')")

        cap.log(
            f"[{label}] LOGIN MODE USED: {mode} "
            f"(expected labels: PROGRAMMATIC / HUMAN / FAILED)"
        )
        cap.log(f"[{label}] Login time (wall): {t_login_wall:.2f}s")
        trig = []
        if signals_after.get("url_changed_vs_human_start"):
            trig.append("URL change")
        if signals_after.get("password_field_gone"):
            trig.append("password field gone")
        if signals_after.get("cookies_nonzero"):
            trig.append("cookies detected")
        if signals_after.get("account_or_logout_found"):
            trig.append("account/logout found")
        cap.log(
            f"[{label}] Post-login snapshot (which signals are TRUE — core may have used any): "
            f"{trig or ['(none of the four)']}"
        )

        cap.log(f"[{label}] === run_ecommerce_scan() START ===")
        scan_started = time.perf_counter()
        scan_result = await run_ecommerce_scan(page, FLOWS, creds_full, cap.log)
        scan_ended = time.perf_counter()
        scan_wall = scan_ended - scan_started
        cap.log(f"[{label}] === run_ecommerce_scan() END === wall_s={scan_wall:.2f}")

    except Exception as e:
        cap.log(f"[{label}] FATAL ERROR (not suppressed): {type(e).__name__}: {e!s}")
        logger.exception("%s fatal", label)
        raise
    finally:
        await page.close()

    total_wall = scan_ended - scan_started if scan_ended else 0.0
    defects = scan_result.get("defects") or []
    actions = scan_result.get("actions") or []
    metrics = scan_result.get("metrics") or {}

    bounds = _parse_flow_boundaries(cap.entries)
    cap.log(f"[{label}] --- FLOW TIMING (from emit boundaries) ---")
    for fk in FLOWS:
        b = bounds.get(fk)
        if b:
            s, e = b
            dur = (e - s) if e is not None else None
            cap.log(f"[{label}]   {fk}: start={s:.2f}s end={e!s} duration={dur}")
            tol = FLOW_TIMEOUTS.get(fk, 15)
            if dur is not None and dur > tol:
                cap.log(f"[{label}]   FLAG: flow {fk} wall {dur:.2f}s > timeout {tol}s")
        else:
            cap.log(f"[{label}]   {fk}: (no boundary parsed)")

    cap.log(f"[{label}] --- TASK 3: PER-FLOW VALIDATION ---")
    for fk in FLOWS:
        fm = metrics.get(fk) if isinstance(metrics, dict) else {}
        if not isinstance(fm, dict):
            fm = {}
        fa = _actions_for_flow(actions, fk)
        fd = _defects_for_flow(defects, fk)
        cap.log(
            f"[{label}] FLOW {fk}: actions={len(fa)} defects={len(fd)} "
            f"metrics_keys={list(fm.keys())}"
        )
        if isinstance(fm, dict) and fm.get("timed_out"):
            cap.log(f"[{label}]   SKIPPED/TIMEOUT: timed_out=True")
        if fk == "auth":
            cap.log(
                f"[{label}]   AUTH: session_validation in actions="
                f"{any(a.get('step')=='session_validation' for a in fa)} "
                f"login_not_persisted={_scan_login_not_persisted(defects)}"
            )
        if fk == "browse":
            nav_ok = any("goto" in str(a.get("step", "")).lower() or "nav" in str(a).lower() for a in fa)
            search_ok = any("search" in str(a.get("step", "")).lower() for a in fa)
            cap.log(f"[{label}]   BROWSE: navigation_signals={nav_ok} search_signals={search_ok}")
        if fk == "cart":
            cap.log(
                f"[{label}]   CART: skipped_requires_login={fm.get('cart_skipped_requires_login')} "
                f"add_to_cart_ok={fm.get('add_to_cart_ok')}"
            )
        if fk == "checkout":
            cap.log(
                f"[{label}]   CHECKOUT: checkout_step signals in actions="
                f"{sum(1 for a in fa if 'checkout' in str(a.get('step','')).lower())}"
            )
        if fk == "support":
            cap.log(
                f"[{label}]   SUPPORT: steps={ [a.get('step') for a in fa][:8] }"
            )
        if fk == "ui":
            cap.log(
                f"[{label}]   UI: ui_defect_count={fm.get('ui_defect_count')} "
                f"timed_out={fm.get('ui_integrity_timed_out')}"
            )

    total_scan = cap.entries[-1][0] if cap.entries else 0.0
    cap.log(f"[{label}] --- TASK 4: TIME ANALYSIS ---")
    cap.log(f"[{label}] Total scan phase (run_ecommerce_scan wall): {total_wall:.2f}s")
    cap.log(f"[{label}] Login wall time: {t_login_wall:.2f}s")
    if total_wall > 90:
        cap.log(f"[{label}] FLAG: Total scan phase > 90s")
    timeout_msgs = [m for m in cap.messages() if "⏱" in m or "timeout" in m.lower() or "timed out" in m.lower()]
    for m in timeout_msgs:
        cap.log(f"[{label}] TIMEOUT/SCAN: {m}")

    cap.log(f"[{label}] --- TASK 5: FAILURE HEURISTICS ---")
    if not login_ok:
        cap.log(f"[{label}]   - Login failed before scan.")
    if login_ok and len([a for a in actions if "valid_login" in str(a.get("step"))]) == 0:
        cap.log(f"[{label}]   - Login reported success but no auth valid_login action in scan (auth flow will re-login).")
    if fp:
        cap.log(f"[{label}]   - False login detection (cookie heuristic) flagged.")
    if metrics.get("cart", {}).get("cart_skipped_requires_login") and not login_ok:
        cap.log(f"[{label}]   - Cart skipped for login while login failed (consistent).")
    if len(defects) == 0:
        cap.log(f"[{label}]   - Zero defects in aggregate (empty results risk).")
    short_flows = [fk for fk in FLOWS if len(_actions_for_flow(actions, fk)) <= 1]
    if short_flows:
        cap.log(f"[{label}]   - Flows with <=1 action: {short_flows}")

    flow_pass: dict[str, bool] = {}
    for fk in FLOWS:
        fm = metrics.get(fk, {}) if isinstance(metrics, dict) else {}
        if not isinstance(fm, dict):
            fm = {}
        fa = _actions_for_flow(actions, fk)
        fd = _defects_for_flow(defects, fk)
        flow_pass[fk] = _flow_passed(fk, fm, fa, fd)

    verdict = _verdict(login_ok, flow_pass, len(defects), len(actions), total_wall)
    issues = _major_issues(site_url, login_ok, str(mode), metrics, defects, actions, fp)

    cap.log("")
    cap.log("==================================")
    cap.log("TEST RESULT SUMMARY")
    cap.log("==================================")
    cap.log(f"Site: {site_url}")
    cap.log(f"Login Mode: {mode}")
    cap.log(f"Login Success: {login_ok}")
    cap.log(f"False Positive Login: {'Yes' if fp else 'No'}")
    cap.log("")
    cap.log("Flows:")
    for fk in FLOWS:
        cap.log(f"- {fk}: {'PASS' if flow_pass.get(fk) else 'FAIL'}")
    cap.log("")
    cap.log("Major Issues:")
    for i, issue in enumerate(issues or ["(none flagged above threshold)"]):
        cap.log(f"  {i+1}. {issue}")
    cap.log("")
    cap.log(f"Total Defects: {len(defects)}")
    cap.log(f"Total Actions: {len(actions)}")
    cap.log(f"Total Time (login + scan walls): {t_login_wall + total_wall:.2f}s")
    cap.log("")
    cap.log(f"System Verdict: {verdict}")

    return {
        "label": label,
        "site_url": site_url,
        "login_ok": login_ok,
        "login_mode": mode,
        "login_wall_s": t_login_wall,
        "scan_wall_s": total_wall,
        "false_positive_login": fp,
        "signals_after_login": signals_after,
        "cookies_before_login": cookies_before,
        "defects": defects,
        "actions": actions,
        "metrics": metrics,
        "flow_pass": flow_pass,
        "verdict": verdict,
        "issues": issues,
        "capture": cap.messages(),
    }


async def _main_async() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )

    results: list[dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # TEST 1
        r1 = await _run_one_test(
            label="TEST 1",
            site_url=url,
            site_creds=credentials,
            context=context,
        )
        results.append(r1)

        # TEST 2
        r2 = await _run_one_test(
            label="TEST 2",
            site_url=url_2,
            site_creds=credentials_2,
            context=context,
        )
        results.append(r2)

        await context.close()
        await browser.close()

    print("\n", flush=True)
    print("============================================================", flush=True)
    print("FINAL COMPARISON (SYSTEM DIAGNOSTIC)", flush=True)
    print("============================================================", flush=True)

    for r in results:
        print(
            f"{r['label']}: verdict={r['verdict']} defects={len(r['defects'])} "
            f"login_ok={r['login_ok']} mode={r['login_mode']}",
            flush=True,
        )

    better = "Inconclusive (compare verdicts and defect counts manually)"
    if results[0]["verdict"] == "WORKING" and results[1]["verdict"] != "WORKING":
        better = f"TEST 1 ({results[0]['site_url']}) appeared stronger by verdict."
    elif results[1]["verdict"] == "WORKING" and results[0]["verdict"] != "WORKING":
        better = f"TEST 2 ({results[1]['site_url']}) appeared stronger by verdict."
    elif len(results[0]["defects"]) < len(results[1]["defects"]) and results[0]["login_ok"]:
        better = f"TEST 1 had fewer reported defects ({len(results[0]['defects'])}) — not necessarily 'better' quality."
    elif len(results[1]["defects"]) < len(results[0]["defects"]) and results[1]["login_ok"]:
        better = f"TEST 2 had fewer reported defects ({len(results[1]['defects'])}) — not necessarily 'better' quality."

    print(f"\nWhich site worked better? {better}", flush=True)

    login_failed = [r["site_url"] for r in results if not r["login_ok"]]
    print(f"Where login failed? {login_failed or 'Both reported login_ok=True (check modes and messages).'}", flush=True)

    flows_failed = {
        r["label"]: [k for k, v in r["flow_pass"].items() if not v] for r in results
    }
    print(f"Where flows failed? {json.dumps(flows_failed, indent=2)}", flush=True)

    weakest = "Relies on heuristics (DOM, timeouts); failures often surface as zero actions or timeouts — see Major Issues."
    print(f"\nBiggest system weakness? {weakest}", flush=True)

    out_path = "system_diagnostic_report.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "site": r["site_url"],
                        "login_ok": r["login_ok"],
                        "login_mode": r["login_mode"],
                        "verdict": r["verdict"],
                        "metrics": r["metrics"],
                        "defect_count": len(r["defects"]),
                        "action_count": len(r["actions"]),
                        "false_positive_login": r["false_positive_login"],
                    }
                    for r in results
                ],
                f,
                indent=2,
                default=str,
            )
        print(f"\nStructured summary written to {out_path}", flush=True)
    except OSError as e:
        print(f"Could not write {out_path}: {e}", flush=True)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
