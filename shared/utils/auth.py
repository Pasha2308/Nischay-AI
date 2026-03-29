"""Authentication helpers (minimal stubs to keep pipeline runnable).

The crawler/executor are designed to optionally authenticate. This module
implements a conservative default: no automatic login unless explicitly
configured with selectors, and failures are non-fatal.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from shared.models.site_model import AuthFlow


def is_login_page(url: str) -> bool:
    return any(x in url.lower() for x in ["login", "signin", "auth"])


@dataclass
class AuthResult:
    success: bool
    error: str | None = None
    auth_flow: AuthFlow | None = None
    post_login_url: str | None = None


@dataclass
class LoginAttemptResult:
    success: bool
    message: str


async def wait_for_human_login(
    page: Page,
    emit_event: Callable[[str], Awaitable[None]],
    timeout_seconds: int = 180,
) -> None:
    await emit_event("🔐 Browser opened — please log in")
    await emit_event("⏳ Waiting for login (3 minutes)...")

    login_url = page.url
    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time

        if elapsed > timeout_seconds:
            await emit_event("❌ Login timeout")
            raise TimeoutError("Human login timeout")

        current_url = page.url

        if current_url != login_url:
            await emit_event("✅ Login detected via URL change")
            return

        login_form = await page.query_selector("input[type='password']")
        if not login_form:
            await emit_event("✅ Login form disappeared")
            return

        if int(elapsed) % 30 == 0:
            remaining = int(timeout_seconds - elapsed)
            await emit_event(f"⏳ Waiting... {remaining}s left")

        await asyncio.sleep(1)


async def detect_login_page(page: Any) -> bool:
    if is_login_page(page.url or ""):
        return True
    try:
        password_inputs = page.locator("input[type='password']")
        return await password_inputs.count() > 0
    except Exception:
        return False


async def _first_visible_selector(page: Any, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return ""


async def attempt_login(page: Any, username: str, password: str) -> LoginAttemptResult:
    """Fill login form, submit, and verify auth via URL transition."""
    user_sel = await _first_visible_selector(
        page,
        [
            "input[type='email']",
            "input[name*='email' i]",
            "input[name*='user' i]",
            "input[name*='login' i]",
            "input[type='text']",
        ],
    )
    pass_sel = await _first_visible_selector(
        page,
        [
            "input[type='password']",
            "input[name*='pass' i]",
        ],
    )
    submit_sel = await _first_visible_selector(
        page,
        [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Log in')",
            "button:has-text('Sign in')",
            "[role='button'][aria-label*='login' i]",
        ],
    )

    if not (user_sel and pass_sel and submit_sel):
        return LoginAttemptResult(False, "Login form selectors not found")

    await page.fill(user_sel, username)
    await page.fill(pass_sel, password)
    await page.click(submit_sel)

    try:
        await page.wait_for_url(
            lambda u: not is_login_page(str(u)),
            timeout=15000,
        )
    except Exception:
        pass

    if is_login_page(page.url or ""):
        return LoginAttemptResult(False, "Still on login page after timeout")
    return LoginAttemptResult(True, "Login successful")


async def perform_smart_auth(
    context: Any,
    auth_config: Any,
    ai_client: Any | None = None,
    *,
    emit_event: Callable[[str], Awaitable[None]] | None = None,
) -> AuthResult:
    """Human-in-the-loop login with explicit URL-based confirmation."""
    try:
        login_url = getattr(auth_config, "login_url", "") or ""
        username = getattr(auth_config, "username", "") or ""
        password = getattr(auth_config, "password", "") or ""

        if not (login_url and username and password):
            return AuthResult(False, "Auth not configured (missing credentials)")

        page = await context.new_page()
        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        if await detect_login_page(page):

            async def _default_emit(msg: str) -> None:
                print(msg, flush=True)

            emit = emit_event or _default_emit
            await wait_for_human_login(page, emit, timeout_seconds=180)
            post_login_url = page.url
            await page.close()
            return AuthResult(
                True,
                auth_flow=AuthFlow(
                    login_url=login_url,
                    login_method="form",
                    requires_credentials=True,
                    detection_method="manual_human",
                    detected_selectors={},
                ),
                post_login_url=post_login_url,
            )

        post_login_url = page.url
        await page.close()

        return AuthResult(
            True,
            auth_flow=AuthFlow(
                login_url=login_url,
                login_method="form",
                requires_credentials=True,
                detection_method="explicit",
                detected_selectors={},
            ),
            post_login_url=post_login_url,
        )
    except TimeoutError:
        raise
    except Exception as e:
        return AuthResult(False, str(e))


async def authenticate_and_capture_state(
    browser: Any,
    auth_config: Any,
    ai_client: Any | None = None,
    viewport: dict[str, int] | None = None,
    user_agent: str | None = None,
) -> tuple[AuthResult, dict | None]:
    """Login once and return Playwright storageState dict (or None)."""
    context = await browser.new_context(viewport=viewport, user_agent=user_agent)
    try:
        result = await perform_smart_auth(context, auth_config, ai_client=ai_client)
        if not result.success:
            return result, None
        storage = await context.storage_state()
        return result, storage
    finally:
        await context.close()
