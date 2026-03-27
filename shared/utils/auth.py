"""Authentication helpers (minimal stubs to keep pipeline runnable).

The crawler/executor are designed to optionally authenticate. This module
implements a conservative default: no automatic login unless explicitly
configured with selectors, and failures are non-fatal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.models.site_model import AuthFlow


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


async def detect_login_page(page: Any) -> bool:
    url = (page.url or "").lower()
    if "login" in url or "signin" in url:
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
            lambda u: ("login" not in str(u).lower()) and ("signin" not in str(u).lower()),
            timeout=15000,
        )
    except Exception:
        pass

    final_url = (page.url or "").lower()
    if "login" in final_url or "signin" in final_url:
        return LoginAttemptResult(False, "Still on login page after timeout")
    return LoginAttemptResult(True, "Login successful")


async def perform_smart_auth(context: Any, auth_config: Any, ai_client: Any | None = None) -> AuthResult:
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
            for _ in range(90):  # 3 minutes, poll every 2 seconds
                current = (page.url or "").lower()
                if "login" not in current and "signin" not in current:
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
                await page.wait_for_timeout(2000)
            await page.close()
            return AuthResult(False, "MANUAL_LOGIN_TIMEOUT: Login timeout — scan cancelled")

        post_login_url = page.url
        await page.close()

        return AuthResult(
            True,
            auth_flow=AuthFlow(
                login_url=login_url,
                login_method="form",
                requires_credentials=True,
                detection_method="explicit",
                detected_selectors={
                    "username_selector": user_sel,
                    "password_selector": pass_sel,
                    "submit_selector": submit_sel,
                },
            ),
            post_login_url=post_login_url,
        )
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

