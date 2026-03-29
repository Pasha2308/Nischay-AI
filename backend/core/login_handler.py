"""Programmatic login + human fallback for shared Playwright contexts."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from playwright.async_api import Page

EmitEvent = Callable[[str], Awaitable[None]]
LogActionFn = Callable[..., Awaitable[str]]
LogBracketedFn = Callable[..., Awaitable[Any]]

_USER_SELECTORS: list[str] = [
    "input[type='email']",
    "input[name*='email' i]",
    "input[name*='user' i]",
    "input[name*='login' i]",
    "input[autocomplete='username']",
    "input[id*='user' i]",
    "input[id*='email' i]",
    "input[placeholder*='email' i]",
    "input[placeholder*='user' i]",
    "input[type='text']",
]

_PASS_SELECTORS: list[str] = [
    "input[type='password']",
    "input[name*='pass' i]",
    "input[autocomplete='current-password']",
    "input[id*='pass' i]",
]

_SUBMIT_SELECTORS: list[str] = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Login')",
    "button:has-text('Log in')",
    "button:has-text('Sign in')",
    "button:has-text('Sign In')",
    "[role='button'][aria-label*='login' i]",
    "form button[type='submit']",
]

_CAPTCHA_KEYWORDS = ("captcha", "recaptcha", "hcaptcha")


def _credential_username_password(credentials: dict[str, Any]) -> tuple[str, str]:
    u = (
        credentials.get("username")
        or credentials.get("user")
        or credentials.get("email")
        or credentials.get("login")
        or ""
    )
    p = credentials.get("password") or credentials.get("pass") or ""
    return str(u).strip(), str(p)


async def _first_matching_visible_selector(page: Page, selectors: list[str]) -> str | None:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


async def _page_text_and_html_lower(page: Page) -> str:
    try:
        html = await page.content()
    except Exception:
        html = ""
    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""
    return (html + "\n" + text).lower()


def _has_captcha_signal(content_lower: str) -> bool:
    return any(k in content_lower for k in _CAPTCHA_KEYWORDS)


async def page_has_captcha(page: Page) -> bool:
    low = await _page_text_and_html_lower(page)
    return _has_captcha_signal(low)


async def _password_field_count(page: Page) -> int:
    try:
        return await page.locator("input[type='password']").count()
    except Exception:
        return 0


async def _detect_login_success(page: Page, url_before_action: str) -> bool:
    try:
        current = page.url or ""
    except Exception:
        current = ""
    if current.strip() and current != url_before_action:
        return True
    n = await _password_field_count(page)
    return n == 0


async def wait_for_human_login(
    page: Page,
    emit_event: EmitEvent,
    *,
    reason: str = "manual",
    timeout_seconds: int = 180,
    log_action: LogActionFn | None = None,
) -> bool:
    """
    Wait until the user completes login: URL changes or password fields disappear.
    Emits progress periodically. Returns True on success, False on timeout.
    """
    await emit_event(f"Human login required ({reason}) — please complete sign-in in the browser")
    if log_action:
        await log_action(
            page,
            phase="login",
            action_type="detect",
            description=f"wait_for_human_login start ({reason})",
            target_url=page.url if page else "",
        )
    try:
        start_url = page.url or ""
    except Exception:
        start_url = ""
    had_password_start = await _password_field_count(page) > 0
    await emit_event(f"Initial URL: {start_url or '(empty)'} (password fields: {int(had_password_start)})")

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    last_progress = -1

    while True:
        elapsed = loop.time() - t0
        if elapsed >= timeout_seconds:
            await emit_event("Human login timed out")
            if log_action:
                await log_action(
                    page,
                    phase="login",
                    action_type="detect",
                    description="wait_for_human_login timed out",
                    target_url=page.url if page else "",
                    outcome="failed",
                    outcome_detail="timeout",
                    duration_ms=int((loop.time() - t0) * 1000),
                )
            return False

        try:
            cur = page.url or ""
        except Exception:
            cur = ""

        if cur.strip() and cur != start_url:
            await emit_event("Login success detected: URL changed")
            if log_action:
                await log_action(
                    page,
                    phase="login",
                    action_type="detect",
                    description="human login success (URL change)",
                    target_url=cur,
                    duration_ms=int((loop.time() - t0) * 1000),
                )
            return True

        pw_count = await _password_field_count(page)
        if had_password_start and pw_count == 0:
            await emit_event("Login success detected: password field disappeared")
            if log_action:
                await log_action(
                    page,
                    phase="login",
                    action_type="detect",
                    description="human login success (password field gone)",
                    target_url=cur,
                    duration_ms=int((loop.time() - t0) * 1000),
                )
            return True

        sec = int(elapsed)
        if sec != last_progress and sec > 0 and sec % 30 == 0:
            last_progress = sec
            remaining = max(0, int(timeout_seconds - elapsed))
            await emit_event(f"Still waiting for human login… {remaining}s remaining")

        await asyncio.sleep(1)


async def perform_programmatic_login(
    page: Page,
    credentials: dict[str, Any],
    emit_event: EmitEvent,
    *,
    log_action: LogActionFn | None = None,
    log_bracketed: LogBracketedFn | None = None,
) -> bool:
    """
    Fill username/password with resilient selectors, submit, and verify success.
    On CAPTCHA, missing form, or failed submit → wait_for_human_login.
    Returns True if authenticated, False if human path times out.
    """
    await emit_event("Starting programmatic login")
    user, password = _credential_username_password(credentials)
    if not user or not password:
        await emit_event("Missing username or password in credentials — switching to human login")
        return await wait_for_human_login(page, emit_event, reason="missing_credentials")

    low = await _page_text_and_html_lower(page)
    if _has_captcha_signal(low):
        await emit_event("CAPTCHA detected (captcha/recaptcha/hcaptcha) — cannot automate; waiting for human")
        return await wait_for_human_login(page, emit_event, reason="captcha", log_action=log_action)

    user_sel = await _first_matching_visible_selector(page, _USER_SELECTORS)
    pass_sel = await _first_matching_visible_selector(page, _PASS_SELECTORS)
    submit_sel = await _first_matching_visible_selector(page, _SUBMIT_SELECTORS)

    if not user_sel or not pass_sel:
        await emit_event("Could not find username and/or password fields — waiting for human")
        return await wait_for_human_login(
            page, emit_event, reason="form_not_found", log_action=log_action
        )

    url_before = page.url
    await emit_event(f"Filling credentials (user selector: {user_sel})")
    try:
        await page.fill(user_sel, user)
        await emit_event("Username filled")
        await page.fill(pass_sel, password)
        await emit_event("Password filled")
    except Exception as e:
        await emit_event(f"Failed to fill form: {e!s} — waiting for human")
        if log_action:
            await log_action(
                page,
                phase="login",
                action_type="fill",
                description="Login fill failed",
                outcome="failed",
                outcome_detail=str(e)[:400],
            )
        return await wait_for_human_login(page, emit_event, reason="fill_error", log_action=log_action)

    low2 = await _page_text_and_html_lower(page)
    if _has_captcha_signal(low2):
        await emit_event("CAPTCHA appeared after fill — waiting for human")
        return await wait_for_human_login(
            page, emit_event, reason="captcha_after_fill", log_action=log_action
        )

    await emit_event("Submitting login form")
    try:
        if submit_sel and log_bracketed:

            async def _submit_click() -> None:
                await page.click(submit_sel, timeout=15_000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20_000)
                except Exception:
                    pass
                await asyncio.sleep(0.4)

            await log_bracketed(
                page,
                phase="login",
                action_type="submit",
                description="Login submit click",
                target_element=submit_sel,
                coro=_submit_click,
            )
        elif submit_sel:
            await page.click(submit_sel, timeout=15_000)
        elif log_bracketed:

            async def _submit_enter() -> None:
                await page.keyboard.press("Enter")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20_000)
                except Exception:
                    pass
                await asyncio.sleep(0.4)

            await log_bracketed(
                page,
                phase="login",
                action_type="submit",
                description="Login submit (Enter key)",
                coro=_submit_enter,
            )
        else:
            await page.keyboard.press("Enter")
    except Exception as e:
        await emit_event(f"Submit click failed ({e!s}) — trying Enter")
        try:
            await page.keyboard.press("Enter")
        except Exception as e2:
            await emit_event(f"Submit failed: {e2!s} — waiting for human")
            if log_action:
                await log_action(
                    page,
                    phase="login",
                    action_type="submit",
                    description="Login submit failed",
                    outcome="failed",
                    outcome_detail=str(e2)[:400],
                )
            return await wait_for_human_login(
                page, emit_event, reason="submit_error", log_action=log_action
            )

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except Exception:
        pass
    await asyncio.sleep(0.4)

    if await _detect_login_success(page, url_before):
        await emit_event("Programmatic login succeeded (URL change or password field cleared)")
        if log_action:
            await log_action(
                page,
                phase="login",
                action_type="detect",
                description="Programmatic login success verification",
                target_url=page.url,
            )
        return True

    await emit_event("Login outcome unclear after submit — waiting for human to finish")
    return await wait_for_human_login(
        page, emit_event, reason="post_submit_unclear", log_action=log_action
    )
