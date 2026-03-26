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


async def perform_smart_auth(context: Any, auth_config: Any, ai_client: Any | None = None) -> AuthResult:
    """Attempt a simple form login if selectors are provided; otherwise no-op."""
    try:
        login_url = getattr(auth_config, "login_url", "") or ""
        username = getattr(auth_config, "username", "") or ""
        password = getattr(auth_config, "password", "") or ""
        user_sel = getattr(auth_config, "username_selector", "") or ""
        pass_sel = getattr(auth_config, "password_selector", "") or ""
        submit_sel = getattr(auth_config, "submit_selector", "") or ""

        if not (login_url and username and password and user_sel and pass_sel and submit_sel):
            return AuthResult(False, "Auth not configured (missing selectors/credentials)")

        page = await context.new_page()
        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        await page.fill(user_sel, username)
        await page.fill(pass_sel, password)
        await page.click(submit_sel)
        await page.wait_for_timeout(1500)
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

