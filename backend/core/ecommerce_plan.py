"""E-commerce scan orchestration — dispatches flow runners with a shared contract."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page

from backend.core.action_engine import capture_console_errors
from backend.core.login_handler import handle_login

logger = logging.getLogger(__name__)


def make_safe_emitter(emit_event):
    """
    Returns a safe async emit function.
    Works whether emit_event is: async function, sync function, or None.
    Never raises. Never crashes the scan.
    """

    async def _emit(message: str):
        if emit_event is None:
            print(message, flush=True)
            return
        try:
            result = emit_event(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            print(f"[emit warning] {message}", flush=True)

    return _emit


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

EmitEvent = Callable[[str], Awaitable[None]]

EcommerceFlowResult = dict[str, Any]
"""Each flow returns ``{\"defects\": list, \"actions\": list, \"metrics\": dict}``."""


def _flow_result(
    *,
    defects: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> EcommerceFlowResult:
    return {
        "defects": defects or [],
        "actions": actions or [],
        "metrics": metrics or {},
    }


async def run_flow_with_timeout(flow_fn, page, credentials, emit, timeout_seconds):
    try:
        return await asyncio.wait_for(
            flow_fn(page, credentials, emit),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        await emit(f"⏱ Flow timeout after {timeout_seconds}s")
        return {"defects": [], "actions": [], "metrics": {"timed_out": True}}
    except Exception as e:
        await emit(f"⚠️ Flow error: {str(e)[:60]}")
        return {"defects": [], "actions": [], "metrics": {"error": str(e)}}



_INVALID_PROBE_EMAIL = "nishcay_invalid_probe@invalid.local"
_INVALID_PROBE_PASSWORD = "WrongProbe!9z"

_LOGOUT_SELECTORS: list[str] = [
    'a[href*="logout" i]',
    'a[href*="signout" i]',
    'a[href*="log-out" i]',
    "text=Log out",
    "text=Sign out",
    "text=Logout",
    "button:has-text('Log out')",
    "button:has-text('Sign out')",
]


def _auth_defect(
    *,
    defect_id: str,
    severity: str,
    impact: str,
    description: str,
    page_url: str,
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "severity": severity,
        "impact": impact,
        "page_url": page_url,
        "description": description,
    }


async def _discover_login_href_from_dom(page: Page) -> str:
    try:
        href = await page.evaluate("""() => {
          const nodes = Array.from(document.querySelectorAll('a[href]'));
          for (const a of nodes) {
            const t = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            const h = (a.getAttribute('href') || '').trim();
            if (!h || h === '#' || h.toLowerCase().startsWith('javascript:')) continue;
            if (/\\b(log\\s*in|sign\\s*in|signin)\\b/.test(t)) return a.href;
          }
          return '';
        }""")
    except Exception as e:
        logger.debug("discover login href: %s", e)
        return ""
    return str(href or "").strip()


async def _resolve_login_target(page: Page, credentials: dict[str, Any]) -> tuple[str, str]:
    """Return (absolute_url_or_empty, resolution_reason)."""
    lu = str(credentials.get("login_url") or "").strip()
    if lu:
        return lu, "credentials.login_url"

    tu = str(credentials.get("target_url") or "").strip()
    if tu and (not page.url or str(page.url).startswith("about:")):
        try:
            await page.goto(tu, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            logger.debug("goto target_url for login discovery: %s", e)

    discovered = await _discover_login_href_from_dom(page)
    if discovered:
        return discovered, "discovered_dom_link"

    if tu:
        return tu, "credentials.target_url"

    cur = str(page.url or "").strip()
    if cur and not cur.startswith("about:"):
        return cur, "current_page_url"

    return "", "none"


async def _goto_login_page(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
    actions: list[dict[str, Any]],
) -> bool:
    await emit( "🔐 Navigating to login page...")
    target, reason = await _resolve_login_target(page, credentials)
    if not target:
        await emit( "⚠️ Could not resolve a login URL — continuing on current page")
        actions.append(
            {
                "flow": "auth",
                "step": "navigate_login",
                "ok": False,
                "reason": reason,
                "page_url": page.url,
            }
        )
        return False
    try:
        await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(0.2)
        actions.append(
            {
                "flow": "auth",
                "step": "navigate_login",
                "ok": True,
                "target": target,
                "resolution": reason,
                "page_url": page.url,
            }
        )
        await emit( f"🔐 Opened login context: {page.url[:200]}")
        return True
    except Exception as e:
        logger.exception("navigate to login")
        await emit( f"❌ Login navigation failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "navigate_login",
                "ok": False,
                "error": str(e)[:2000],
                "target": target,
                "page_url": getattr(page, "url", "") or "",
            }
        )
        return False


async def _try_logout(page: Page, emit: Any, actions: list[dict[str, Any]]) -> bool:
    await emit( "🚪 Attempting logout (if session is active)...")
    for sel in _LOGOUT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible():
                continue
            url_before = page.url
            await loc.click(timeout=12_000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20_000)
            except Exception:
                pass
            await asyncio.sleep(0.35)
            actions.append(
                {
                    "flow": "auth",
                    "step": "logout",
                    "ok": True,
                    "selector": sel,
                    "url_before": url_before,
                    "page_url": page.url,
                }
            )
            await emit( "🚪 Logout control activated")
            return True
        except Exception as e:
            logger.debug("logout try %s: %s", sel, e)
            continue
    actions.append(
        {
            "flow": "auth",
            "step": "logout",
            "ok": False,
            "detail": "no_logout_control_found",
            "page_url": page.url,
        }
    )
    await emit( "ℹ️ No logout control found or click failed — continuing")
    return False


async def _visible_login_error_signals(page: Page) -> bool:
    try:
        has_alert = await page.evaluate("""() => {
          const alerts = Array.from(document.querySelectorAll('[role="alert"], .error, .invalid-feedback, [class*="error"]'));
          for (const el of alerts) {
            const t = (el.innerText || '').trim();
            if (t.length > 2 && el.offsetParent !== null) return true;
          }
          return false;
        }""")
        if has_alert:
            return True
        body = (await page.inner_text("body")).lower()
        needles = (
            "invalid",
            "incorrect",
            "wrong password",
            "wrong email",
            "could not",
            "couldn't",
            "failed",
            "does not match",
            "do not match",
            "not recognized",
            "unknown user",
            "try again",
        )
        if any(n in body for n in needles):
            return True
        invalid_attr = await page.locator("[aria-invalid='true']").count()
        return invalid_attr > 0
    except Exception as e:
        logger.debug("login error signals: %s", e)
        return False


async def _invalid_credentials_probe(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> bool:
    """Return True if invalid credentials appear handled (error surfaced)."""
    await emit( "🔴 Testing invalid credentials (probe)...")
    user_sel = await _first_matching_visible_selector(page, _USER_SELECTORS)
    pass_sel = await _first_matching_visible_selector(page, _PASS_SELECTORS)
    submit_sel = await _first_matching_visible_selector(page, _SUBMIT_SELECTORS)
    if not user_sel or not pass_sel:
        await emit( "⚠️ Skipping invalid-credential probe — username/password fields not found")
        actions.append(
            {
                "flow": "auth",
                "step": "invalid_credentials",
                "ok": False,
                "skipped": True,
                "reason": "missing_fields",
                "page_url": page.url,
            }
        )
        return False
    try:
        await page.fill(user_sel, _INVALID_PROBE_EMAIL)
        await page.fill(pass_sel, _INVALID_PROBE_PASSWORD)
        if submit_sel:
            await page.click(submit_sel, timeout=15_000)
        else:
            await page.keyboard.press("Enter")
        await asyncio.sleep(0.6)
        handled = await _visible_login_error_signals(page)
        actions.append(
            {
                "flow": "auth",
                "step": "invalid_credentials",
                "ok": True,
                "error_message_visible": handled,
                "page_url": page.url,
            }
        )
        if not handled:
            defects.append(
                _auth_defect(
                    defect_id="missing_error_message",
                    severity="high",
                    impact="trust",
                    description="Submitted known-invalid credentials but no clear error/validation feedback detected",
                    page_url=page.url,
                )
            )
            await emit( "⚠️ Invalid login did not surface an obvious error message")
        else:
            await emit( "✅ Invalid credentials produced a visible error state")
        return handled
    except Exception as e:
        logger.exception("invalid credentials probe")
        await emit( f"❌ Invalid credential probe failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "invalid_credentials",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )
        return False


async def _empty_form_probe(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> bool:
    """Return True if empty submit appears validated (HTML5 or messaging)."""
    await emit( "📭 Testing empty form submission...")
    user_sel = await _first_matching_visible_selector(page, _USER_SELECTORS)
    pass_sel = await _first_matching_visible_selector(page, _PASS_SELECTORS)
    submit_sel = await _first_matching_visible_selector(page, _SUBMIT_SELECTORS)
    if not user_sel or not pass_sel:
        await emit( "⚠️ Skipping empty-form probe — fields not found")
        actions.append(
            {
                "flow": "auth",
                "step": "empty_form",
                "ok": False,
                "skipped": True,
                "page_url": page.url,
            }
        )
        return False
    try:
        await page.fill(user_sel, "")
        await page.fill(pass_sel, "")
        if submit_sel:
            await page.click(submit_sel, timeout=15_000)
        else:
            await page.keyboard.press("Enter")
        await asyncio.sleep(0.45)
        has_html5 = await page.evaluate("""() => {
          const els = Array.from(document.querySelectorAll('input, select, textarea'));
          return els.some((el) => typeof el.checkValidity === 'function' && !el.checkValidity() && el.offsetParent !== null);
        }""")
        has_invalid = (await page.locator(":invalid").count()) > 0
        msg = await _visible_login_error_signals(page)
        ok = bool(has_html5 or has_invalid or msg)
        actions.append(
            {
                "flow": "auth",
                "step": "empty_form",
                "ok": True,
                "validation_observed": ok,
                "page_url": page.url,
            }
        )
        if not ok:
            defects.append(
                _auth_defect(
                    defect_id="missing_required_validation",
                    severity="medium",
                    impact="ux",
                    description="Empty login submit did not show HTML5 validity, :invalid state, or error messaging",
                    page_url=page.url,
                )
            )
            await emit( "⚠️ Empty submit did not show required-field validation")
        else:
            await emit( "✅ Empty form triggered validation or error feedback")
        return ok
    except Exception as e:
        logger.exception("empty form probe")
        await emit( f"❌ Empty form probe failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "empty_form",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )
        return False


async def _signup_probe(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> bool:
    await emit( "📝 Looking for signup / registration entry points...")
    found = False
    try:
        info = await page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('a[href]').forEach((a) => {
            const t = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            const h = (a.getAttribute('href') || '').trim();
            if (/sign\\s*up|register|create\\s+account|join\\s+now/.test(t)) {
              out.push({ text: t.slice(0, 120), href: h.slice(0, 500) });
            }
          });
          return { matches: out.slice(0, 20), count: out.length };
        }""")
        count = int(info.get("count") or 0)
        found = count > 0
        actions.append(
            {
                "flow": "auth",
                "step": "signup_discovery",
                "ok": True,
                "signup_link_candidates": count,
                "page_url": page.url,
            }
        )
        if not found:
            defects.append(
                _auth_defect(
                    defect_id="no_signup_found",
                    severity="medium",
                    impact="revenue",
                    description="No obvious signup/register/create-account link found on the page",
                    page_url=page.url,
                )
            )
            await emit( "⚠️ No signup link found in DOM scan")
        else:
            await emit( f"✅ Found {count} signup-like link(s)")
    except Exception as e:
        logger.exception("signup probe")
        await emit( f"❌ Signup discovery failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "signup_discovery",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )
    return found


async def _password_reset_probe(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
) -> tuple[bool, str]:
    await emit( "🔑 Probing password reset / forgot-password flow...")
    url_before = page.url
    detail = "not_attempted"
    try:
        href_or_none = await page.evaluate("""() => {
          const nodes = Array.from(document.querySelectorAll('a[href]'));
          for (const a of nodes) {
            const t = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            const h = (a.getAttribute('href') || '').trim();
            if (!h || h === '#') continue;
            if (/forgot|reset\\s*password|password\\s*reset/.test(t)) return a.href;
          }
          return '';
        }""")
        if not href_or_none:
            actions.append(
                {
                    "flow": "auth",
                    "step": "password_reset",
                    "ok": False,
                    "detail": "no_forgot_link",
                    "page_url": page.url,
                }
            )
            await emit( "ℹ️ No forgot-password link found on this page")
            return False, "no_link"

        abs_url = urljoin(url_before, str(href_or_none))
        await page.goto(abs_url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(0.25)
        has_email = await page.locator(
            "input[type='email'], input[name*='email' i], input[autocomplete='email']"
        ).count()
        reset_like = await page.evaluate("""() => {
          const t = (document.body.innerText || '').toLowerCase();
          return /reset|forgot|recover/.test(t);
        }""")
        ok = bool(has_email > 0 or reset_like)
        detail = "reset_page_opened" if ok else "navigated_but_unclear"
        actions.append(
            {
                "flow": "auth",
                "step": "password_reset",
                "ok": True,
                "navigated_to": page.url,
                "email_field_visible": has_email > 0,
                "reset_copy_detected": reset_like,
                "page_url": page.url,
            }
        )
        await emit(
            f"🔑 Password reset path opened — email_field={has_email > 0}, reset_copy={reset_like}",
        )
        return ok, detail
    except Exception as e:
        logger.exception("password reset probe")
        await emit( f"❌ Password reset probe failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "password_reset",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )
        return False, str(e)[:500]


async def run_auth_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    metrics: dict[str, Any] = {
        "login_tested": False,
        "invalid_cred_handled": False,
        "signup_found": False,
        "password_reset_found": False,
        "auth_defects": 0,
    }

    async def _relay(msg: str) -> None:
        await emit( msg)

    # 1) Navigate to login
    try:
        await _goto_login_page(page, credentials, emit, actions)
    except Exception as e:
        await emit( f"❌ Navigate step crashed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "navigate_login",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )

    # 2) Valid login
    login_ok = False
    try:
        await emit( "✅ Attempting valid login (programmatic)...")
        metrics["login_tested"] = True
        _login_creds: dict[str, Any] = {
            "username": (
                credentials.get("username")
                or credentials.get("email")
                or credentials.get("user")
                or ""
            ),
            "password": credentials.get("password") or credentials.get("pass") or "",
            "login_url": credentials.get("login_url") or page.url,
        }
        login_ok = await handle_login(page, _login_creds, _relay)
        actions.append(
            {
                "flow": "auth",
                "step": "valid_login",
                "success": bool(login_ok),
                "page_url": page.url,
            }
        )
        if not login_ok:
            defects.append(
                _auth_defect(
                    defect_id="login_failure",
                    severity="critical",
                    impact="revenue",
                    description="Valid credentials did not complete authentication in handle_login",
                    page_url=page.url,
                )
            )
            await emit( "❌ Valid login did not complete")
        else:
            await emit( "✅ Valid login completed")
            await emit( "🔍 Validating session...")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=45_000)
                await asyncio.sleep(0.5)
                has_account_or_logout = await page.query_selector(
                    "a:has-text('Logout'), a:has-text('Account')"
                )
                login_form_password = await page.query_selector(
                    "input[type='password']"
                )
                login_confirmed = bool(has_account_or_logout) and (
                    login_form_password is None
                )
                actions.append(
                    {
                        "flow": "auth",
                        "step": "session_validation",
                        "ok": login_confirmed,
                        "page_url": page.url,
                    }
                )
                if not login_confirmed:
                    defects.append(
                        _auth_defect(
                            defect_id="login_not_persisted",
                            severity="high",
                            impact="trust",
                            description=(
                                "Session not confirmed after reload: need account/logout "
                                "control and no login password field."
                            ),
                            page_url=page.url,
                        )
                    )
                    await emit( "❌ Session not confirmed after reload")
                else:
                    await emit( "✅ Session validated after reload")
            except Exception as e:
                logger.exception("session validation after login")
                defects.append(
                    _auth_defect(
                        defect_id="login_not_persisted",
                        severity="high",
                        impact="trust",
                        description=f"Session validation failed: {e!s}"[:4000],
                        page_url=page.url,
                    )
                )
                actions.append(
                    {
                        "flow": "auth",
                        "step": "session_validation",
                        "ok": False,
                        "error": str(e)[:2000],
                        "page_url": page.url,
                    }
                )
                await emit( f"❌ Session validation error: {e!s}")
    except Exception as e:
        logger.exception("valid login")
        await emit( f"❌ Valid login raised: {e!s}")
        defects.append(
            _auth_defect(
                defect_id="login_failure",
                severity="critical",
                impact="revenue",
                description=f"Login flow error: {e!s}"[:4000],
                page_url=page.url,
            )
        )
        actions.append(
            {
                "flow": "auth",
                "step": "valid_login",
                "success": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )

    # 3) Logout
    try:
        await _try_logout(page, emit, actions)
    except Exception as e:
        logger.exception("logout")
        await emit( f"❌ Logout step crashed: {e!s}")
        actions.append(
            {"flow": "auth", "step": "logout", "ok": False, "error": str(e)[:2000], "page_url": page.url}
        )

    # Re-open login page for abuse tests
    try:
        await emit( "🔐 Returning to login page for credential-edge tests...")
        await _goto_login_page(page, credentials, emit, actions)
    except Exception as e:
        await emit( f"❌ Re-navigation to login failed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "navigate_login_retry",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )

    # 4) Invalid credentials
    try:
        metrics["invalid_cred_handled"] = await _invalid_credentials_probe(
            page, emit, actions, defects
        )
    except Exception as e:
        logger.exception("invalid cred")
        await emit( f"❌ Invalid credential step crashed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "invalid_credentials",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )

    # 5) Empty form (refresh login context for a clean submit)
    try:
        await emit( "🔐 Refreshing login page before empty-form test...")
        await _goto_login_page(page, credentials, emit, actions)
        await _empty_form_probe(page, emit, actions, defects)
    except Exception as e:
        logger.exception("empty form")
        await emit( f"❌ Empty form step crashed: {e!s}")
        actions.append(
            {
                "flow": "auth",
                "step": "empty_form",
                "ok": False,
                "error": str(e)[:2000],
                "page_url": page.url,
            }
        )

    # 6) Signup
    try:
        metrics["signup_found"] = await _signup_probe(page, emit, actions, defects)
    except Exception as e:
        logger.exception("signup")
        await emit( f"❌ Signup step crashed: {e!s}")
        actions.append(
            {"flow": "auth", "step": "signup_discovery", "ok": False, "error": str(e)[:2000], "page_url": page.url}
        )

    # 7) Password reset (navigate back to login if we left the page)
    try:
        pr_ok, _pr_detail = await _password_reset_probe(page, emit, actions)
        metrics["password_reset_found"] = bool(pr_ok)
    except Exception as e:
        logger.exception("password reset")
        await emit( f"❌ Password reset step crashed: {e!s}")
        actions.append(
            {"flow": "auth", "step": "password_reset", "ok": False, "error": str(e)[:2000], "page_url": page.url}
        )

    metrics["auth_defects"] = len(defects)
    await emit( f"📊 Auth flow finished — {metrics['auth_defects']} defect(s) recorded")

    return _flow_result(defects=defects, actions=actions, metrics=metrics)


def _browse_defect(
    *,
    defect_id: str,
    impact: str,
    description: str,
    page_url: str,
    severity: str = "medium",
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "impact": impact,
        "severity": severity,
        "page_url": page_url,
        "description": description,
    }


def _cart_defect(
    *,
    defect_id: str,
    impact: str,
    description: str,
    page_url: str,
    severity: str = "high",
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "impact": impact,
        "severity": severity,
        "page_url": page_url,
        "description": description,
    }


def _checkout_defect(
    *,
    defect_id: str,
    impact: str,
    description: str,
    page_url: str,
    severity: str = "high",
    risk_weight: str = "high",
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "impact": impact,
        "severity": severity,
        "risk_weight": risk_weight,
        "page_url": page_url,
        "description": description,
    }


def _support_defect(
    *,
    defect_id: str,
    impact: str,
    description: str,
    page_url: str,
    severity: str = "medium",
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "impact": impact,
        "severity": severity,
        "page_url": page_url,
        "description": description,
    }


def _ui_defect(
    *,
    defect_id: str,
    impact: str,
    description: str,
    page_url: str,
    severity: str = "medium",
) -> dict[str, Any]:
    return {
        "defect": defect_id,
        "type": defect_id,
        "impact": impact,
        "severity": severity,
        "page_url": page_url,
        "description": description,
    }


def _parse_money_label(s: str | None) -> float | None:
    if not s or not str(s).strip():
        return None
    cleaned = re.sub(r"[^\d.]", "", str(s).replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _checkout_summary_amounts(page: Page) -> dict[str, float | None]:
    raw = await page.evaluate("""() => {
      const t = document.body.innerText || '';
      const grab = (labels) => {
        for (const lab of labels) {
          const re = new RegExp(lab + '[\\\\s:]*([\\\\$€£₹]?\\\\s*[\\\\d,]+\\\\.?\\\\d*)', 'i');
          const m = t.match(re);
          if (m) return m[1].trim();
        }
        return '';
      };
      return {
        subtotal: grab(['Subtotal', 'Sub-total', 'Sub total']),
        tax: grab(['Tax', 'Estimated tax', 'Sales tax', 'VAT', 'GST']),
        shipping: grab(['Shipping', 'Delivery', 'Shipping & handling']),
        total: grab(['Order total', 'Total', 'Amount due', 'Grand total']),
      };
    }""")
    return {
        "subtotal": _parse_money_label(str(raw.get("subtotal") or "")),
        "tax": _parse_money_label(str(raw.get("tax") or "")),
        "shipping": _parse_money_label(str(raw.get("shipping") or "")),
        "total": _parse_money_label(str(raw.get("total") or "")),
    }


async def _browse_maybe_goto_start(
    page: Page, credentials: dict[str, Any], emit: Any, actions: list[dict[str, Any]]
) -> None:
    base = str(
        credentials.get("browse_start_url")
        or credentials.get("target_url")
        or credentials.get("base_url")
        or ""
    ).strip()
    if not base:
        return
    try:
        await emit( f"🛒 Browse: opening storefront — {base[:120]}")
        await page.goto(base, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(0.25)
        actions.append({"flow": "browse", "step": "goto_start", "ok": True, "url": base, "page_url": page.url})
    except Exception as e:
        logger.exception("browse goto start")
        await emit( f"❌ Browse: could not open start URL: {e!s}")
        actions.append(
            {"flow": "browse", "step": "goto_start", "ok": False, "error": str(e)[:2000], "page_url": page.url}
        )


async def _page_signals_not_found_or_error(page: Page) -> bool:
    try:
        title = (await page.title()).lower()
        snippet = (await page.inner_text("body"))[:12_000].lower()
    except Exception:
        return False
    title_hits = ("404", "not found", "page not found", "error")
    if any(h in title for h in title_hits):
        return True
    body_needles = (
        "404 error",
        "page not found",
        "this page could not be found",
        "we can't find",
        "doesn't exist",
        "http 404",
    )
    return any(n in snippet for n in body_needles)


_SEARCH_INPUT_SELECTORS: list[str] = [
    "input[type='search']",
    "input[name*='search' i]",
    "input[id*='search' i]",
    "input[placeholder*='search' i]",
    "input[aria-label*='search' i]",
    "[data-testid*='search' i] input",
    "form[role='search'] input",
]


async def _first_visible_search_input(page: Page) -> str | None:
    for sel in _SEARCH_INPUT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


async def _count_listing_items(page: Page) -> int:
    try:
        return int(
            await page.evaluate("""() => {
              const sels = [
                '[class*="product" i]', '[data-product-id]', '[data-product]',
                'article[class*="product" i]', '.product', '.product-card',
                'li[class*="product" i]', '[class*="ProductCard" i]', '[class*="product-tile" i]',
              ];
              let best = 0;
              for (const s of sels) {
                try {
                  const n = document.querySelectorAll(s).length;
                  if (n > best) best = n;
                } catch (e) {}
              }
              return best;
            }""")
        )
    except Exception:
        return 0


async def _browse_nav_probe(
    page: Page,
    emit: Any,
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    flow_key: str = "browse",
) -> None:
    await emit( "🧭 Browse: testing main navigation links...")
    start_url = page.url
    try:
        links = await page.evaluate("""() => {
          const root = document.querySelector('nav, [role="navigation"], header') || document.body;
          const out = [];
          root.querySelectorAll('a[href]').forEach((a) => {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || a.getAttribute('aria-label') || '').trim();
            if (!h || h === '#' || h.toLowerCase().startsWith('javascript:')) return;
            if (t.length < 2 || t.length > 100) return;
            out.push({ href: a.href, text: t.slice(0, 80) });
          });
          return out.slice(0, 12);
        }""")
    except Exception as e:
        await emit( f"❌ Nav discovery failed: {e!s}")
        actions.append({"flow": flow_key, "step": "main_navigation", "ok": False, "error": str(e)[:2000]})
        return

    if not links:
        await emit( "ℹ️ No navigation links collected — skipping nav clicks")
        actions.append({"flow": flow_key, "step": "main_navigation", "ok": True, "clicks": 0, "reason": "no_links"})
        return

    max_clicks = min(5, len(links))
    broken = 0
    for i in range(max_clicks):
        item = links[i]
        href = str(item.get("href") or "")
        text = str(item.get("text") or "")
        try:
            await emit( f"🧭 Nav click [{i + 1}/{max_clicks}]: {text[:50]}")
            await page.goto(href, wait_until="domcontentloaded", timeout=25_000)
            await asyncio.sleep(0.2)
            bad = await _page_signals_not_found_or_error(page)
            if bad:
                broken += 1
                defects.append(
                    _browse_defect(
                        defect_id="broken_navigation",
                        impact="UX",
                        description=f"Navigation target appears broken or not found after following: {text[:120]}",
                        page_url=page.url,
                        severity="medium",
                    )
                )
                await emit( f"⚠️ Possible broken page after nav: {page.url[:100]}")
            actions.append(
                {
                    "flow": flow_key,
                    "step": "main_navigation",
                    "ok": not bad,
                    "index": i,
                    "link_text": text[:200],
                    "result_url": page.url,
                }
            )
        except Exception as e:
            broken += 1
            defects.append(
                _browse_defect(
                    defect_id="broken_navigation",
                    impact="UX",
                    description=f"Navigation click/navigation failed: {text[:80]} — {e!s}"[:4000],
                    page_url=start_url,
                    severity="medium",
                )
            )
            actions.append(
                {
                    "flow": flow_key,
                    "step": "main_navigation",
                    "ok": False,
                    "index": i,
                    "error": str(e)[:2000],
                }
            )
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=25_000)
            await asyncio.sleep(0.15)
        except Exception:
            pass

    await emit( f"🧭 Main navigation pass complete — {broken} broken signal(s)")
    actions.append({"flow": flow_key, "step": "main_navigation_summary", "broken_signals": broken})


async def _browse_search_probe(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    valid: bool,
    flow_key: str = "browse",
) -> None:
    label = "valid" if valid else "invalid"
    await emit( f"🔎 Browse: search with {label} query...")
    sel = await _first_visible_search_input(page)
    if not sel:
        await emit( "⚠️ No search input found — skipping search step")
        actions.append({"flow": flow_key, "step": f"search_{label}", "ok": False, "skipped": True})
        if valid:
            defects.append(
                _browse_defect(
                    defect_id="search_failure",
                    impact="Revenue",
                    description="Could not locate a search field to run product search",
                    page_url=page.url,
                    severity="high",
                )
            )
        return

    if valid:
        q = str(
            credentials.get("browse_search_query")
            or credentials.get("product_keyword")
            or credentials.get("search_query")
            or "shirt"
        ).strip() or "shirt"
    else:
        q = f"nishcay_bogus_{secrets.token_hex(8)}"

    try:
        await page.fill(sel, "")
        await page.fill(sel, q)
        await asyncio.sleep(0.1)
        await page.keyboard.press("Enter")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:
            pass
        await asyncio.sleep(0.45)

        listing = await _count_listing_items(page)
        body_low = (await page.inner_text("body"))[:14_000].lower()

        if valid:
            ok = listing >= 1 or any(
                x in body_low
                for x in ("result", "product", "item", "match", "found", "showing")
            )
            actions.append(
                {
                    "flow": flow_key,
                    "step": "search_valid",
                    "ok": ok,
                    "query": q[:120],
                    "listing_like_count": listing,
                    "page_url": page.url,
                }
            )
            if not ok:
                defects.append(
                    _browse_defect(
                        defect_id="search_failure",
                        impact="Revenue",
                        description=f"Search for {q!r} did not show obvious results or product listings",
                        page_url=page.url,
                        severity="high",
                    )
                )
                await emit( "⚠️ Valid search may have failed to return results")
            else:
                await emit( "✅ Valid search returned plausible results")
        else:
            empty_signals = (
                "no result",
                "no match",
                "no product",
                "nothing found",
                "0 result",
                "did not match",
                "couldn't find",
                "could not find",
                "no items",
                "we couldn't find",
                "sorry, no",
            )
            has_empty = any(s in body_low for s in empty_signals)
            server_err = await page.evaluate("""() => {
              const t = (document.body.innerText || '').toLowerCase();
              return /\\b500\\b|internal server|something went wrong|error occurred/.test(t);
            }""")
            if server_err:
                ok = False
            elif has_empty or listing <= 2:
                ok = True
            else:
                ok = False
            actions.append(
                {
                    "flow": flow_key,
                    "step": "search_invalid",
                    "ok": ok,
                    "query": q[:120],
                    "listing_like_count": listing,
                    "empty_state_detected": has_empty,
                    "page_url": page.url,
                }
            )
            if not ok:
                defects.append(
                    _browse_defect(
                        defect_id="empty_state_missing",
                        impact="UX",
                        description="Invalid search: no clear empty state and listing still looks full, or server text detected",
                        page_url=page.url,
                        severity="medium",
                    )
                )
                await emit( "⚠️ Invalid search empty state unclear or error page")
            else:
                await emit( "✅ Invalid search handled (empty state, sparse results, or no error)")

    except Exception as e:
        logger.exception("browse search %s", label)
        await emit( f"❌ Search ({label}) failed: {e!s}")
        actions.append({"flow": flow_key, "step": f"search_{label}", "ok": False, "error": str(e)[:2000]})
        defects.append(
            _browse_defect(
                defect_id="search_failure" if valid else "empty_state_missing",
                impact="Revenue" if valid else "UX",
                description=f"Search flow error ({label}): {e!s}"[:4000],
                page_url=page.url,
                severity="high" if valid else "medium",
            )
        )


async def _browse_filters_probe(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> None:
    await emit( "🎚️ Browse: trying category / filter controls...")
    before = await _count_listing_items(page)
    clicked = False
    check_loc = page.locator(
        'aside input[type="checkbox"], .filters input[type="checkbox"], '
        '[class*="filter" i] input[type="checkbox"], [data-filter] input[type="checkbox"]'
    )
    try:
        n = await check_loc.count()
        for i in range(min(n, 6)):
            try:
                box = check_loc.nth(i)
                if not await box.is_visible():
                    continue
                await box.click(timeout=5000)
                clicked = True
                await asyncio.sleep(0.5)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(0.35)
                break
            except Exception:
                continue
    except Exception as e:
        actions.append({"flow": "browse", "step": "filters", "ok": False, "error": str(e)[:2000]})
        await emit( f"ℹ️ Filter interaction failed: {e!s}")
        return

    if not clicked:
        await emit( "ℹ️ No filter checkbox found — skipping")
        actions.append({"flow": "browse", "step": "filters", "ok": True, "skipped": True, "reason": "no_checkbox"})
        return

    after = await _count_listing_items(page)
    changed = before != after
    actions.append(
        {
            "flow": "browse",
            "step": "filters",
            "ok": True,
            "listing_before": before,
            "listing_after": after,
            "listing_changed": changed,
            "page_url": page.url,
        }
    )
    if not changed:
        defects.append(
            _browse_defect(
                defect_id="filter_not_working",
                impact="Revenue",
                description="Applied a filter control but product-like listing count did not change (heuristic)",
                page_url=page.url,
                severity="high",
            )
        )
        await emit( "⚠️ Filter may not have updated the listing")
    else:
        await emit( "✅ Listing count changed after filter")


async def _browse_scroll_probe(
    page: Page, emit: Any, actions: list[dict[str, Any]]
) -> None:
    await emit( "📜 Browse: scrolling product listing...")
    before = await _count_listing_items(page)
    height = await page.evaluate("() => document.body.scrollHeight || 0")
    try:
        await page.evaluate("() => window.scrollBy(0, Math.min(2000, window.innerHeight * 3))")
        await asyncio.sleep(0.6)
        await page.evaluate("() => window.scrollBy(0, Math.min(2000, window.innerHeight * 3))")
        await asyncio.sleep(0.8)
        after = await _count_listing_items(page)
        has_more = after > before
        pag = await page.evaluate("""() => {
          const t = document.body.innerText.toLowerCase();
          return {
            next: !!document.querySelector('a[rel="next"], [aria-label*="next" i], .pagination a'),
            loadMore: /load more|show more/.test(t),
          };
        }""")
        mode = "infinite_scroll" if has_more else ("pagination" if pag.get("next") else "static_or_unknown")
        actions.append(
            {
                "flow": "browse",
                "step": "scroll_listing",
                "ok": True,
                "listing_before": before,
                "listing_after": after,
                "scroll_height": height,
                "pagination_hint": bool(pag.get("next")),
                "load_more_hint": bool(pag.get("loadMore")),
                "mode_guess": mode,
                "page_url": page.url,
            }
        )
        await emit( f"📜 Scroll probe — mode guess: {mode}")
    except Exception as e:
        actions.append({"flow": "browse", "step": "scroll_listing", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Scroll probe failed: {e!s}")


async def _browse_product_detail_probe(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> None:
    await emit( "📦 Browse: opening a product detail page...")
    listing_url = page.url
    try:
        pdp = await page.evaluate("""() => {
          const sels = [
            'a[href*="/product"]', 'a[href*="/item"]', 'a[href*="/p/"]', '[data-product-url]',
            'article a[href]', '.product a[href]', '[class*="product-tile" i] a',
          ];
          for (const s of sels) {
            const a = document.querySelector(s);
            if (a && a.href) return a.href;
          }
          const links = Array.from(document.querySelectorAll('main a[href], [role="main"] a[href]'));
          for (const a of links) {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || '').trim();
            if (h.length > 3 && t.length > 2 && t.length < 120) return a.href;
          }
          return '';
        }""")
    except Exception as e:
        actions.append({"flow": "browse", "step": "product_detail", "ok": False, "error": str(e)[:2000]})
        return

    if not pdp:
        defects.append(
            _browse_defect(
                defect_id="product_page_incomplete",
                impact="Revenue",
                description="Could not find a product link to open product detail",
                page_url=page.url,
                severity="high",
            )
        )
        await emit( "⚠️ No product link found for PDP check")
        actions.append({"flow": "browse", "step": "product_detail", "ok": False, "skipped": True})
        return

    try:
        await page.goto(str(pdp), wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(0.35)
    except Exception as e:
        defects.append(
            _browse_defect(
                defect_id="broken_navigation",
                impact="UX",
                description=f"Failed to open product URL: {e!s}"[:4000],
                page_url=listing_url,
                severity="medium",
            )
        )
        actions.append({"flow": "browse", "step": "product_detail", "ok": False, "error": str(e)[:2000]})
        return

    chk = await page.evaluate("""() => {
      const body = (document.body.innerText || '').toLowerCase();
      const priceRe = /(\\$|€|£|₹|usd|eur|gbp|rs\\.?\\s*\\d|\\d+\\.\\d{2}\\s*(usd|eur)?)/i;
      const imgs = Array.from(document.querySelectorAll('img')).filter((img) => {
        const r = img.getBoundingClientRect();
        return r.width >= 80 && r.height >= 80 && (img.complete ? img.naturalWidth > 0 : true);
      });
      const cartBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).some((el) => {
        const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
        return /add to cart|add to bag|buy now|purchase/.test(t);
      });
      return {
        image_ok: imgs.length > 0,
        image_count: imgs.length,
        price_ok: priceRe.test(body) || !!document.querySelector('[class*="price" i], [itemprop="price"]'),
        add_to_cart: cartBtn,
      };
    }""")

    actions.append(
        {
            "flow": "browse",
            "step": "product_detail",
            "ok": True,
            "pdp_url": page.url,
            "checks": chk,
        }
    )

    missing: list[str] = []
    if not chk.get("image_ok"):
        missing.append("images")
    if not chk.get("price_ok"):
        missing.append("price")
    if not chk.get("add_to_cart"):
        missing.append("add_to_cart")

    if missing:
        defects.append(
            _browse_defect(
                defect_id="product_page_incomplete",
                impact="Revenue",
                description=f"Product page missing expected elements: {', '.join(missing)}",
                page_url=page.url,
                severity="high",
            )
        )
        await emit( f"⚠️ PDP incomplete: {missing}")
    else:
        await emit( "✅ PDP shows image(s), price signal, and add-to-cart")


async def run_browse_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Simulate product discovery: nav, search, filters, scroll, and PDP checks."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "browse", "step": "start", "page_url": page.url}]

    await _browse_maybe_goto_start(page, credentials, emit, actions)

    try:
        await _browse_nav_probe(page, emit, defects, actions)
    except Exception as e:
        logger.exception("browse nav")
        await emit( f"❌ Main navigation step crashed: {e!s}")
        actions.append({"flow": "browse", "step": "main_navigation", "ok": False, "error": str(e)[:2000]})

    try:
        await _browse_search_probe(page, credentials, emit, defects, actions, valid=True)
    except Exception as e:
        logger.exception("browse search valid")
        await emit( f"❌ Valid search step crashed: {e!s}")

    try:
        await _browse_search_probe(page, credentials, emit, defects, actions, valid=False)
    except Exception as e:
        logger.exception("browse search invalid")
        await emit( f"❌ Invalid search step crashed: {e!s}")

    try:
        await _browse_filters_probe(page, emit, defects, actions)
    except Exception as e:
        logger.exception("browse filters")
        await emit( f"❌ Filters step crashed: {e!s}")
        actions.append({"flow": "browse", "step": "filters", "ok": False, "error": str(e)[:2000]})

    try:
        await _browse_scroll_probe(page, emit, actions)
    except Exception as e:
        logger.exception("browse scroll")
        await emit( f"❌ Scroll step crashed: {e!s}")

    try:
        await _browse_product_detail_probe(page, emit, defects, actions)
    except Exception as e:
        logger.exception("browse pdp")
        await emit( f"❌ Product detail step crashed: {e!s}")
        actions.append({"flow": "browse", "step": "product_detail", "ok": False, "error": str(e)[:2000]})

    metrics = {
        "browse_defect_count": len(defects),
        "final_url": page.url,
        "defect_types": sorted({str(d.get("defect")) for d in defects if isinstance(d, dict)}),
    }
    await emit( f"📊 Browse flow complete — {len(defects)} defect(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def _broken_href_candidates(
    page: Page,
    *,
    label: str,
    text_needles: tuple[str, ...],
    href_needles: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Flag visible links whose text/href suggests a surface but href is unusable."""

    data = await page.evaluate(
        """({ textNeedles, hrefNeedles }) => {
          const tns = (textNeedles || []).map((s) => String(s).toLowerCase());
          const hns = (hrefNeedles || []).map((s) => String(s).toLowerCase());
          const bad = (h) => {
            const x = (h || '').trim();
            return !x || x === '#' || x.toLowerCase().startsWith('javascript:');
          };
          const out = [];
          document.querySelectorAll('a[href]').forEach((a) => {
            const text = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            const href = (a.getAttribute('href') || '').trim();
            const lowHref = href.toLowerCase();
            const matchText = tns.some((n) => n && text.includes(n));
            const matchHref = hns.some((n) => n && lowHref.includes(n));
            if ((matchText || matchHref) && bad(href)) {
              out.push({ text: text.slice(0, 200), href: href.slice(0, 500) });
            }
          });
          return out.slice(0, 40);
        }""",
        {"textNeedles": list(text_needles), "hrefNeedles": list(href_needles)},
    )
    defects: list[dict[str, Any]] = []
    url = page.url
    for row in data:
        defects.append(
            {
                "defect": "broken_or_missing_href",
                "type": label,
                "severity": "medium",
                "page_url": url,
                "description": f"Link matches {label} intent but href is empty, '#', or javascript: — {row!r}",
            }
        )
    return defects


async def _cart_snapshot(page: Page) -> dict[str, Any]:
    try:
        return await page.evaluate("""() => {
          const text = document.body.innerText || '';
          let badge = 0;
          document.querySelectorAll(
            '[data-cart-count], [data-count], [class*="cart-count" i], [class*="MiniCart" i] [class*="count" i], header .badge, a[href*="cart"] .badge'
          ).forEach((el) => {
            const raw = (el.innerText || '').replace(/[^0-9]/g, ' ');
            const nums = raw.trim().split(/\\s+/).filter(Boolean).map((x) => parseInt(x, 10));
            nums.forEach((n) => { if (!isNaN(n) && n < 1000) badge = Math.max(badge, n); });
          });
          const lineSelectors = [
            '[class*="cart-item" i]', '[class*="CartLine" i]', '[data-line-item]', '[data-cart-line]',
            'table.cart tbody tr', '.cart__line', 'li.cart-item', '[class*="line-item" i]',
          ];
          let lines = 0;
          for (const s of lineSelectors) {
            try {
              const c = document.querySelectorAll(s).length;
              if (c > lines) lines = c;
            } catch (e) {}
          }
          const subMatch = text.match(/subtotal[:\\s\\n]*([\\$€£₹]?\\s*[\\d,]+\\.?\\d*)/i);
          const totMatch = text.match(/(?:^|[^\\w])total[:\\s\\n]*([\\$€£₹]?\\s*[\\d,]+\\.?\\d*)/im);
          return {
            badgeMax: badge,
            lineItems: lines,
            subtotalMoney: subMatch ? subMatch[1].trim() : '',
            totalMoney: totMatch ? totMatch[1].trim() : '',
          };
        }""")
    except Exception:
        return {"badgeMax": 0, "lineItems": 0, "subtotalMoney": "", "totalMoney": ""}


async def _cart_pdp_requires_login(page: Page) -> bool:
    """Heuristic: PDP expects sign-in before adding to cart."""
    try:
        low = (await page.inner_text("body", timeout=10_000)).lower()
    except Exception:
        low = ""
    phrases = (
        "sign in to add",
        "log in to add",
        "login to add",
        "must sign in",
        "must log in",
        "sign in to purchase",
        "log in to purchase",
        "create an account to add",
        "register to add",
    )
    if any(p in low for p in phrases):
        return True
    try:
        has_add = await page.locator(
            "button:has-text('Add to cart'), button:has-text('Add to bag')"
        ).count()
        has_signin = await page.locator("a:has-text('Sign in'), a:has-text('Log in')").count()
        if has_signin > 0 and has_add == 0:
            return True
    except Exception:
        pass
    return False


async def _cart_has_logged_in_session(page: Page) -> bool:
    """Logged-in chrome: account / logout / sign out visible."""
    try:
        el = await page.query_selector(
            "a:has-text('Logout'), a:has-text('Sign out'), "
            "a:has-text('Account'), a:has-text('My account')"
        )
        return el is not None
    except Exception:
        return False


async def _cart_find_pdp_url(page: Page) -> str:
    try:
        pdp = await page.evaluate("""() => {
          const sels = [
            'a[href*="/product"]', 'a[href*="/item"]', 'a[href*="/p/"]', '[data-product-url]',
            'article a[href]', '.product a[href]', '[class*="product-tile" i] a',
          ];
          for (const s of sels) {
            const a = document.querySelector(s);
            if (a && a.href) return a.href;
          }
          const links = Array.from(document.querySelectorAll('main a[href], [role="main"] a[href]'));
          for (const a of links) {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || '').trim();
            if (h.length > 3 && t.length > 2 && t.length < 120) return a.href;
          }
          return '';
        }""")
    except Exception:
        return ""
    return str(pdp or "").strip()


async def _cart_find_cart_page_url(page: Page, base: str) -> str:
    try:
        href = await page.evaluate("""() => {
          const nodes = Array.from(document.querySelectorAll('a[href*="cart" i], a[href*="basket" i], a[href*="bag" i]'));
          for (const a of nodes) {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            if (!h || h === '#' || h.toLowerCase().startsWith('javascript:')) continue;
            if (/(cart|basket|bag|checkout)/i.test(h) || /view|cart|bag/.test(t)) return a.href;
          }
          return '';
        }""")
    except Exception:
        href = ""
    if href:
        return str(href).strip()
    if base:
        return urljoin(base.rstrip("/") + "/", "cart")
    return ""


async def _cart_open_cart_page(
    page: Page, credentials: dict[str, Any], emit: Any, actions: list[dict[str, Any]]
) -> str:
    base = str(
        credentials.get("browse_start_url") or credentials.get("target_url") or credentials.get("base_url") or ""
    ).strip()
    cart_url = await _cart_find_cart_page_url(page, base)
    if not cart_url:
        await emit( "⚠️ Cart: could not resolve cart page URL")
        actions.append({"flow": "cart", "step": "open_cart", "ok": False, "page_url": page.url})
        return ""
    try:
        await page.goto(cart_url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(0.35)
        actions.append({"flow": "cart", "step": "open_cart", "ok": True, "cart_url": page.url})
        await emit( f"🛒 Cart page: {page.url[:120]}")
        return page.url
    except Exception as e:
        await emit( f"❌ Cart: open cart failed: {e!s}")
        actions.append({"flow": "cart", "step": "open_cart", "ok": False, "error": str(e)[:2000]})
        return ""


async def run_cart_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """
    Cart: find a PDP, aggressively click add-to-cart, open cart — optimized for demo sites
    (e.g. automationexercise.com) with clear product and cart affordances.
    """
    actions: list[dict[str, Any]] = [{"flow": "cart", "step": "start", "page_url": page.url}]
    defects: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "add_to_cart_ok": False,
        "quantity_updated": False,
        "cart_persistent": False,
        "promo_tested": False,
        "cart_defects": 0,
    }

    try:
        parsed = urlparse(page.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else page.url
    except Exception:
        parts = page.url.split("/")
        base_url = parts[0] + "//" + parts[2] if len(parts) > 2 else page.url

    await emit("🛒 Cart: finding a product to add...")

    product_url = None
    product_selectors = [
        "a[href*='/product']",
        "a[href*='/products']",
        "a[href*='/item']",
        ".product a",
        "[class*='product'] a",
        ".card a",
        "[class*='card'] a",
    ]

    for sel in product_selectors:
        try:
            links = await page.eval_on_selector_all(
                sel, "els => els.map(e => e.href).filter(h => h && !h.includes('#'))"
            )
            if links:
                product_url = links[0]
                break
        except Exception:
            continue

    if not product_url:
        await emit("⚠️ No product link found — trying homepage products")
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1000)
            links = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href).filter(h => /product|item|shop|details/i.test(h))",
            )
            if links:
                product_url = links[0]
        except Exception:
            pass

    if product_url:
        await emit(f"🛒 Opening product page: {str(product_url)[:60]}")
        try:
            await page.goto(product_url, wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
        except Exception:
            await emit("⚠️ Product page load timeout — using current page")

    await emit("⚡ Attempting to add product to cart...")
    add_to_cart_selectors = [
        "button:has-text('Add to cart')",
        "button:has-text('Add to Cart')",
        "button:has-text('ADD TO CART')",
        "button:has-text('Add To Bag')",
        "button:has-text('Add to bag')",
        "button:has-text('Buy now')",
        "[data-testid*='add-to-cart' i]",
        "[id*='add-to-cart' i]",
        "[class*='add-to-cart' i]",
        "button[name='add']",
        ".btn-cart",
        "#add-to-cart",
    ]

    cart_added = False
    for sel in add_to_cart_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible(timeout=2000):
                await btn.click(timeout=4000)
                await page.wait_for_timeout(2000)
                cart_added = True
                metrics["add_to_cart_ok"] = True
                actions.append(
                    {
                        "flow": "cart",
                        "step": "add_to_cart",
                        "type": "click",
                        "description": f"Clicked add-to-cart ({sel})",
                        "outcome": "success",
                        "page_url": page.url,
                    }
                )
                await emit("✅ Product added to cart successfully")
                break
        except Exception:
            continue

    if not cart_added:
        await emit("⚠️ Could not add to cart — button not found or not clickable")
        defects.append(
            _cart_defect(
                defect_id="add_to_cart_failure",
                impact="Revenue",
                description="Add to cart button not found or unresponsive on product page",
                page_url=page.url,
                severity="critical",
            )
        )

    await emit("🔍 Verifying cart state...")
    cart_selectors = [
        "a[href*='/cart']",
        "[class*='cart' i]",
        "[href*='cart' i]",
        "button:has-text('Cart')",
        "a[href*='view_cart']",
    ]

    for sel in cart_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=3000)
                await page.wait_for_timeout(1500)
                metrics["cart_persistent"] = True
                await emit("✅ Cart opened successfully")
                actions.append(
                    {
                        "flow": "cart",
                        "step": "open_cart",
                        "type": "navigate",
                        "description": "Opened cart page",
                        "outcome": "success",
                        "page_url": page.url,
                    }
                )
                break
        except Exception:
            continue

    metrics["cart_defects"] = len(defects)
    await emit(f"📊 Cart flow complete — {len(defects)} issue(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)



async def safe_click(page, selector, timeout_ms=3000, *, nth=None):
    try:
        loc = page.locator(selector)
        el = loc.first if nth is None else loc.nth(nth)
        await el.click(timeout=timeout_ms)
        return True
    except:
        return False


async def safe_fill(page, selector, value, timeout_ms=3000):
    try:
        el = page.locator(selector).first
        await el.fill(value, timeout=timeout_ms)
        return True
    except:
        return False


def _checkout_shipping_fixture(credentials: dict[str, Any]) -> dict[str, str]:
    return {
        "first": str(credentials.get("shipping_first_name") or credentials.get("first_name") or "Test").strip(),
        "last": str(credentials.get("shipping_last_name") or credentials.get("last_name") or "Customer").strip(),
        "address1": str(
            credentials.get("shipping_address")
            or credentials.get("address")
            or "123 Commerce Street"
        ).strip(),
        "city": str(credentials.get("shipping_city") or credentials.get("city") or "San Francisco").strip(),
        "zip": str(
            credentials.get("shipping_zip") or credentials.get("zip") or credentials.get("postal") or "94102"
        ).strip(),
        "phone": str(credentials.get("shipping_phone") or credentials.get("phone") or "5550100999").strip(),
        "email": str(
            credentials.get("shipping_email") or credentials.get("email") or "checkout@example.com"
        ).strip(),
        "country": str(credentials.get("shipping_country") or credentials.get("country") or "United States").strip(),
    }


async def _checkout_navigate_to_checkout(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> bool:
    await emit( "💳 Step 1: Proceed to checkout...")
    base = str(credentials.get("target_url") or credentials.get("base_url") or "").strip()
    cart_url = await _cart_find_cart_page_url(page, base)
    if cart_url:
        try:
            await page.goto(cart_url, wait_until="domcontentloaded", timeout=35_000)
            await asyncio.sleep(0.35)
        except Exception as e:
            logger.debug("checkout open cart: %s", e)

    url_before = page.url
    clicked = False
    for sel in (
        "a:has-text('Proceed to checkout')",
        "button:has-text('Proceed to checkout')",
        "button:has-text('Checkout')",
        "a:has-text('Checkout')",
        "[data-checkout]",
        "a[href*='checkout']:visible",
    ):
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0 or not await loc.is_visible():
                continue
            if await safe_click(page, sel, timeout_ms=15_000):
                clicked = True
                break
        except Exception:
            continue

    if not clicked and base:
        try:
            co = urljoin(base.rstrip("/") + "/", "checkout")
            await page.goto(co, wait_until="domcontentloaded", timeout=30_000)
            clicked = True
        except Exception:
            pass

    if clicked:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=25_000)
        except Exception:
            pass
        await asyncio.sleep(0.45)

    if await _page_signals_not_found_or_error(page):
        defects.append(
            _checkout_defect(
                defect_id="checkout_blocked",
                impact="Revenue",
                description="Checkout navigation landed on a not-found or error page",
                page_url=page.url,
                severity="critical",
                risk_weight="maximum",
            )
        )
        await emit( "❌ Checkout redirect blocked or error page")
        actions.append({"flow": "checkout", "step": "proceed_checkout", "ok": False, "page_url": page.url})
        return False

    ok = "checkout" in page.url.lower() or page.url != url_before
    if not ok and not clicked:
        defects.append(
            _checkout_defect(
                defect_id="checkout_blocked",
                impact="Revenue",
                description="Could not find Proceed to checkout control or /checkout URL",
                page_url=page.url,
                severity="critical",
                risk_weight="maximum",
            )
        )
        actions.append({"flow": "checkout", "step": "proceed_checkout", "ok": False})
        await emit( "❌ Could not reach checkout")
        return False

    actions.append({"flow": "checkout", "step": "proceed_checkout", "ok": True, "page_url": page.url})
    await emit( f"✅ Checkout URL: {page.url[:140]}")
    return True


async def _checkout_fill_shipping_all(
    page: Page, data: dict[str, str], emit: Any, actions: list[dict[str, Any]]
) -> bool:
    await emit( "💳 Step 2: Filling shipping form...")
    filled = 0
    tries: list[tuple[str, str]] = [
        ("input#firstName, input[name*='first'], input[autocomplete='given-name']", data["first"]),
        ("input#lastName, input[name*='last'], input[autocomplete='family-name']", data["last"]),
        (
            "input[name*='address']:not([name*='line2']), input[autocomplete='address-line1']",
            data["address1"],
        ),
        ("input[name*='city'], input[autocomplete='address-level2']", data["city"]),
        ("input[name*='zip'], input[name*='postal'], input[autocomplete='postal-code']", data["zip"]),
        ("input[type='tel'], input[name*='phone'], input[autocomplete='tel']", data["phone"]),
        ("input[type='email'], input[autocomplete='email']", data["email"]),
    ]
    for sel, val in tries:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0 or not await loc.is_visible():
                continue
            if await safe_fill(page, sel, val, timeout_ms=3000):
                filled += 1
        except Exception:
            continue
    try:
        country_sel = page.locator("select[name*='country'], select[autocomplete='country']").first
        if await country_sel.count() and await country_sel.is_visible():
            try:
                await country_sel.select_option(label=data["country"])
                filled += 1
            except Exception:
                try:
                    await country_sel.select_option(index=1)
                    filled += 1
                except Exception:
                    pass
    except Exception:
        pass

    actions.append({"flow": "checkout", "step": "fill_shipping", "fields_filled": filled, "page_url": page.url})
    await emit( f"💳 Shipping fields filled: {filled}")
    return filled >= 4


async def _checkout_validation_incomplete_submit(
    page: Page,
    emit: Any,
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> bool:
    await emit( "💳 Step 3: Validation — submit incomplete form...")
    try:
        for name in ("zip", "postal", "email"):
            try:
                loc = page.locator(f"input[name*='{name}']").first
                if await loc.count() and await loc.is_visible():
                    await safe_fill(page, f"input[name*='{name}']", "", timeout_ms=3000)
            except Exception:
                continue
        submitted = False
        for txt in ("Continue", "Continue to shipping", "Next", "Proceed", "Save"):
            try:
                if await safe_click(page, f"button:has-text('{txt}')", timeout_ms=6000):
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            if await safe_click(page, "input[type='submit']", timeout_ms=6000):
                submitted = True
        await asyncio.sleep(0.45)
        body = (await page.inner_text("body"))[:10_000].lower()
        invalid_n = await page.locator(":invalid").count()
        alerts = await page.locator("[role='alert'], .error, .field-error, [class*='error']").count()
        keywords = (
            "required",
            "invalid",
            "enter",
            "please",
            "must",
            "missing",
            "error",
            "cannot",
        )
        has_msg = any(k in body for k in keywords)
        ok = invalid_n > 0 or alerts > 0 or has_msg
        actions.append(
            {
                "flow": "checkout",
                "step": "validation_incomplete",
                "ok": ok,
                "invalid_nodes": invalid_n,
                "alert_nodes": alerts,
                "page_url": page.url,
            }
        )
        if not ok:
            defects.append(
                _checkout_defect(
                    defect_id="validation_missing",
                    impact="UX",
                    description="Incomplete shipping submit did not surface validation errors (heuristic)",
                    page_url=page.url,
                    severity="medium",
                    risk_weight="high",
                )
            )
            await emit( "⚠️ No obvious validation for incomplete form")
        else:
            await emit( "✅ Validation feedback detected")
        return ok
    except Exception as e:
        actions.append({"flow": "checkout", "step": "validation_incomplete", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Validation probe error: {e!s}")
        return False


async def _checkout_select_shipping_method(
    page: Page, emit: Any, actions: list[dict[str, Any]]
) -> bool:
    await emit( "💳 Step 4: Shipping method — verify total updates...")
    before = await _checkout_summary_amounts(page)
    try:
        radios = page.locator(
            'input[type="radio"][name*="shipping"], input[type="radio"][name*="delivery"], '
            'fieldset input[type="radio"]'
        )
        n = await radios.count()
        if n <= 1:
            actions.append({"flow": "checkout", "step": "shipping_method", "ok": True, "skipped": True, "options": n})
            await emit( "ℹ️ Single/no shipping option — skipping compare")
            return True
        sel_radio = (
            'input[type="radio"][name*="shipping"], input[type="radio"][name*="delivery"], '
            'fieldset input[type="radio"]'
        )
        if not await safe_click(page, sel_radio, timeout_ms=8000, nth=min(1, n - 1)):
            raise RuntimeError("shipping radio click failed")
        await asyncio.sleep(0.65)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        after = await _checkout_summary_amounts(page)
        changed = (before.get("total") != after.get("total")) or (before.get("shipping") != after.get("shipping"))
        actions.append(
            {
                "flow": "checkout",
                "step": "shipping_method",
                "ok": True,
                "totals_before": before,
                "totals_after": after,
                "total_changed": changed,
                "page_url": page.url,
            }
        )
        if not changed:
            await emit( "ℹ️ Totals unchanged after shipping switch (may be same price)")
        else:
            await emit( "✅ Totals changed after shipping method")
        return True
    except Exception as e:
        actions.append({"flow": "checkout", "step": "shipping_method", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Shipping method: {e!s}")
        return False


async def _checkout_payment_surface_present(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> bool:
    await emit( "💳 Step 5: Payment fields present...")
    try:
        has = await page.evaluate("""() => {
          const ifr = document.querySelectorAll('iframe[src*="stripe"], iframe[src*="braintree"], iframe[src*="paypal"]').length;
          const card = document.querySelectorAll(
            'input[autocomplete="cc-number"], input[name*="card"], input[name*="Card"], #card-number'
          ).length;
          const cvc = document.querySelectorAll(
            'input[autocomplete="cc-csc"], input[name*="cvv"], input[name*="cvc"]'
          ).length;
          const exp = document.querySelectorAll(
            'input[autocomplete="cc-exp"], input[name*="expir"]'
          ).length;
          const radioPay = Array.from(document.querySelectorAll('input[type="radio"]')).filter(
            (r) => /pay|card|credit|cod/i.test((r.name || '') + (r.id || ''))
          ).length;
          return { iframes: ifr, cardInputs: card, cvcInputs: cvc, expInputs: exp, payRadios: radioPay };
        }""")
        ok = (
            has.get("iframes", 0) > 0
            or has.get("cardInputs", 0) > 0
            or (has.get("cvcInputs", 0) > 0 and has.get("expInputs", 0) > 0)
            or has.get("payRadios", 0) > 0
        )
        actions.append({"flow": "checkout", "step": "payment_fields", "ok": ok, "detail": has, "page_url": page.url})
        if not ok:
            defects.append(
                _checkout_defect(
                    defect_id="payment_missing",
                    impact="Trust",
                    description="No recognizable payment card fields, payment iframes, or payment method controls",
                    page_url=page.url,
                    severity="high",
                    risk_weight="maximum",
                )
            )
            await emit( "⚠️ Payment inputs not detected")
        else:
            await emit( "✅ Payment surface detected")
        return ok
    except Exception as e:
        defects.append(
            _checkout_defect(
                defect_id="payment_missing",
                impact="Trust",
                description=f"Payment check failed: {e!s}"[:4000],
                page_url=page.url,
                severity="high",
                risk_weight="maximum",
            )
        )
        actions.append({"flow": "checkout", "step": "payment_fields", "ok": False, "error": str(e)[:2000]})
        return False


async def _checkout_order_math_and_place_order(
    page: Page,
    emit: Any,
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> None:
    await emit( "💳 Step 6: Order summary math...")
    am = await _checkout_summary_amounts(page)
    sub, tax, ship, tot = am["subtotal"], am["tax"], am["shipping"], am["total"]
    math_ok: bool | None = None
    if sub is not None and tot is not None:
        t_tax = tax if tax is not None else 0.0
        t_ship = ship if ship is not None else 0.0
        expected = sub + t_tax + t_ship
        diff = abs(expected - tot)
        tol = max(0.05, 0.02 * (tot or 1))
        math_ok = diff <= tol or diff / max(tot, 0.01) <= 0.03
        actions.append(
            {
                "flow": "checkout",
                "step": "order_summary_math",
                "ok": math_ok,
                "amounts": am,
                "expected_sum": expected,
                "delta": diff,
                "page_url": page.url,
            }
        )
        if not math_ok:
            defects.append(
                _checkout_defect(
                    defect_id="total_mismatch",
                    impact="Data",
                    description=f"subtotal+tax+shipping ({expected:.2f}) vs total ({tot}) outside tolerance",
                    page_url=page.url,
                    severity="high",
                    risk_weight="high",
                )
            )
            await emit( "⚠️ Order total math mismatch")
        else:
            await emit( "✅ Order totals roughly consistent")
    else:
        actions.append(
            {
                "flow": "checkout",
                "step": "order_summary_math",
                "ok": False,
                "skipped": True,
                "amounts": am,
                "page_url": page.url,
            }
        )
        await emit( "ℹ️ Could not parse enough summary lines for math check")
        math_ok = False

    metrics["total_math_ok"] = bool(math_ok) if math_ok is not None else False

    await emit( "💳 Step 7: Place order button...")
    place_ready = False
    try:
        btn = page.locator(
            "button:has-text('Place order'), button:has-text('Complete order'), "
            "button:has-text('Pay now'), button:has-text('Submit order')"
        ).first
        if await btn.count() == 0:
            defects.append(
                _checkout_defect(
                    defect_id="checkout_blocked",
                    impact="Revenue",
                    description="Place order / complete purchase button not found",
                    page_url=page.url,
                    severity="critical",
                    risk_weight="maximum",
                )
            )
            actions.append({"flow": "checkout", "step": "place_order_button", "ok": False})
            await emit( "⚠️ Place order button not found")
            metrics["place_order_ready"] = False
            return
        enabled = await btn.is_enabled()
        visible = await btn.is_visible()
        place_ready = bool(enabled and visible)
        actions.append(
            {
                "flow": "checkout",
                "step": "place_order_button",
                "ok": place_ready,
                "enabled": enabled,
                "visible": visible,
                "page_url": page.url,
            }
        )
        if not enabled or not visible:
            defects.append(
                _checkout_defect(
                    defect_id="checkout_blocked",
                    impact="Revenue",
                    description="Place order control missing, disabled, or not visible",
                    page_url=page.url,
                    severity="critical",
                    risk_weight="maximum",
                )
            )
            await emit( "⚠️ Place order not enabled/visible")
        else:
            await emit( "✅ Place order button enabled and visible (not clicked)")
    except Exception as e:
        defects.append(
            _checkout_defect(
                defect_id="checkout_blocked",
                impact="Revenue",
                description=f"Place order check failed: {e!s}"[:4000],
                page_url=page.url,
                severity="critical",
                risk_weight="maximum",
            )
        )
        actions.append({"flow": "checkout", "step": "place_order_button", "ok": False, "error": str(e)[:2000]})
        place_ready = False
    metrics["place_order_ready"] = place_ready


async def run_checkout_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """
    High–risk-weight purchase journey: checkout redirect, shipping, validation,
    shipping method, payment surface, totals, place-order control. Does not submit payment.
    """
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "checkout", "step": "start", "page_url": page.url}]
    metrics: dict[str, Any] = {
        "checkout_risk_weight": "maximum",
        "proceed_ok": False,
        "shipping_filled": False,
        "validation_feedback_ok": False,
        "shipping_method_ok": False,
        "payment_surface_ok": False,
        "total_math_ok": False,
        "place_order_ready": False,
        "checkout_defects": 0,
    }

    current_url = page.url
    if any(x in current_url.lower() for x in ["countryselect", "country-select", "region", "locale"]):
        await emit("⚠️ Checkout blocked by region selector")
        return _flow_result(
            defects=[
                _checkout_defect(
                    defect_id="checkout_region_gate",
                    impact="revenue",
                    description="Blocked by region selector",
                    page_url=current_url,
                    severity="high",
                    risk_weight="high",
                )
            ],
            actions=[],
            metrics={"blocked": "region"},
        )

    await _browse_maybe_goto_start(page, credentials, emit, actions)

    try:
        metrics["proceed_ok"] = await _checkout_navigate_to_checkout(
            page, credentials, emit, actions, defects
        )
    except Exception as e:
        logger.exception("checkout proceed")
        await emit( f"❌ Proceed step crashed: {e!s}")
        defects.append(
            _checkout_defect(
                defect_id="checkout_blocked",
                impact="Revenue",
                description=str(e)[:4000],
                page_url=page.url,
                severity="critical",
                risk_weight="maximum",
            )
        )

    if not metrics["proceed_ok"]:
        metrics["checkout_defects"] = len(defects)
        return _flow_result(defects=defects, actions=actions, metrics=metrics)

    ship = _checkout_shipping_fixture(credentials)
    try:
        metrics["shipping_filled"] = await _checkout_fill_shipping_all(page, ship, emit, actions)
    except Exception as e:
        await emit( f"❌ Shipping fill: {e!s}")
        actions.append({"flow": "checkout", "step": "fill_shipping", "ok": False, "error": str(e)[:2000]})

    try:
        metrics["validation_feedback_ok"] = await _checkout_validation_incomplete_submit(
            page, emit, defects, actions
        )
    except Exception as e:
        logger.exception("checkout validation")
        await emit( f"❌ Validation step: {e!s}")

    try:
        await _checkout_fill_shipping_all(page, ship, emit, actions)
    except Exception as e:
        logger.debug("checkout re-fill: %s", e)

    try:
        metrics["shipping_method_ok"] = await _checkout_select_shipping_method(page, emit, actions)
    except Exception as e:
        logger.exception("checkout shipping method")
        await emit( f"❌ Shipping method: {e!s}")

    try:
        metrics["payment_surface_ok"] = await _checkout_payment_surface_present(
            page, emit, defects, actions
        )
    except Exception as e:
        logger.exception("checkout payment")
        await emit( f"❌ Payment step: {e!s}")

    try:
        await _checkout_order_math_and_place_order(page, emit, defects, actions, metrics)
    except Exception as e:
        logger.exception("checkout math/place")
        await emit( f"❌ Summary/place order: {e!s}")

    metrics["checkout_defects"] = len(defects)
    co_actions = [a for a in actions if a.get("flow") == "checkout"]
    if len(co_actions) < 3 and len(defects) == 0:
        defects.append(
            _checkout_defect(
                defect_id="checkout_insufficient_coverage",
                impact="Revenue",
                description="Checkout produced fewer than 3 actions and no defects",
                page_url=page.url,
                severity="medium",
                risk_weight="high",
            )
        )
        metrics["checkout_defects"] = len(defects)
    await emit( f"📊 Checkout flow complete — {len(defects)} defect(s)")

    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def _support_discover_help_url(page: Page) -> str:
    try:
        href = await page.evaluate("""() => {
          const nodes = Array.from(document.querySelectorAll('a[href]'));
          for (const a of nodes) {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase();
            if (!h || h === '#' || h.toLowerCase().startsWith('javascript:')) continue;
            if (/\\/(faq|help|support|contact)/i.test(h) || /faq|help|support|contact/.test(t)) {
              return a.href;
            }
          }
          return '';
        }""")
    except Exception:
        return ""
    return str(href or "").strip()


async def _support_open_help_faq(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> bool:
    await emit( "💬 Help/FAQ: opening support page...")
    explicit = str(
        credentials.get("support_url") or credentials.get("help_url") or credentials.get("faq_url") or ""
    ).strip()
    base = str(credentials.get("target_url") or credentials.get("base_url") or "").strip()

    if explicit:
        try:
            await page.goto(explicit, wait_until="domcontentloaded", timeout=35_000)
            await asyncio.sleep(0.35)
            if not await _page_signals_not_found_or_error(page):
                actions.append(
                    {"flow": "support", "step": "open_help_faq", "ok": True, "via": "credentials", "url": page.url}
                )
                await emit( f"✅ Help URL: {page.url[:120]}")
                return True
        except Exception as e:
            logger.debug("support explicit url: %s", e)

    if base:
        try:
            await page.goto(base, wait_until="domcontentloaded", timeout=35_000)
            await asyncio.sleep(0.25)
        except Exception:
            pass

    discovered = await _support_discover_help_url(page)
    if discovered:
        try:
            await page.goto(discovered, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(0.35)
            if not await _page_signals_not_found_or_error(page):
                actions.append(
                    {"flow": "support", "step": "open_help_faq", "ok": True, "via": "discovered", "url": page.url}
                )
                await emit( f"✅ Opened discovered help link: {page.url[:120]}")
                return True
        except Exception as e:
            logger.debug("support discovered: %s", e)

    if base:
        for path in ("/help", "/faq", "/support", "/contact", "/pages/contact"):
            try:
                u = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
                await page.goto(u, wait_until="domcontentloaded", timeout=22_000)
                await asyncio.sleep(0.3)
                if not await _page_signals_not_found_or_error(page):
                    actions.append(
                        {"flow": "support", "step": "open_help_faq", "ok": True, "via": "path_guess", "url": page.url}
                    )
                    await emit( f"✅ Help via path {path}: {page.url[:100]}")
                    return True
            except Exception:
                continue

    defects.append(
        _support_defect(
            defect_id="support_unreachable",
            impact="Trust",
            description="Could not open a help, FAQ, or contact page (explicit URL, discovery, or common paths)",
            page_url=page.url,
            severity="high",
        )
    )
    actions.append({"flow": "support", "step": "open_help_faq", "ok": False})
    await emit( "❌ Help/FAQ page not reachable")
    return False


async def _support_test_live_chat(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> None:
    await emit( "💬 Testing live chat widget...")
    iframe_before = 0
    try:
        iframe_before = await page.locator("iframe").count()
    except Exception:
        pass

    launchers = (
        "button:has-text('Chat')",
        "button:has-text('Live chat')",
        "[class*='chat-launcher']",
        "[id*='Intercom']",
        "[data-testid*='chat']",
        "[aria-label*='chat']",
        "text=Chat",
    )
    clicked = False
    for sel in launchers:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible():
                continue
            await loc.click(timeout=8000)
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        has_iframe = await page.evaluate("""() => {
          return Array.from(document.querySelectorAll('iframe')).some((f) => {
            const s = (f.src || '').toLowerCase();
            return /intercom|drift|zendesk|hubspot|crisp|tawk|livechat|olark|chat/.test(s);
          });
        }""")
        actions.append(
            {
                "flow": "support",
                "step": "live_chat",
                "ok": True,
                "skipped": True,
                "reason": "no_launcher",
                "embedded_chat_iframe": has_iframe,
                "page_url": page.url,
            }
        )
        await emit( "ℹ️ No chat launcher — skipping chat interaction")
        return

    await asyncio.sleep(1.0)
    try:
        iframe_after = await page.locator("iframe").count()
    except Exception:
        iframe_after = iframe_before

    chat_iframe = await page.evaluate("""() => {
      return Array.from(document.querySelectorAll('iframe')).filter((f) => {
        const s = (f.src || '').toLowerCase();
        return /intercom|drift|zendesk|hubspot|crisp|tawk|livechat|olark|chat|widget/.test(s);
      }).length;
    }""")
    expanded = await page.evaluate("""() => {
      const el = document.querySelector('[class*="chat"], [id*="chat"], [role="dialog"]');
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.width > 80 && r.height > 80 && window.getComputedStyle(el).visibility !== 'hidden';
    }""")

    ok = iframe_after > iframe_before or chat_iframe > 0 or expanded
    actions.append(
        {
            "flow": "support",
            "step": "live_chat",
            "ok": ok,
            "iframe_delta": iframe_after - iframe_before,
            "chat_iframe_count": chat_iframe,
            "widget_visible": expanded,
            "page_url": page.url,
        }
    )
    if not ok:
        defects.append(
            _support_defect(
                defect_id="chat_not_working",
                impact="Support",
                description="Chat launcher clicked but no chat iframe or visible widget detected",
                page_url=page.url,
                severity="high",
            )
        )
        await emit( "⚠️ Chat widget may not have opened")
    else:
        await emit( "✅ Chat surface detected after launch")


async def _support_submit_contact_form(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> None:
    await emit( "💬 Submitting support/contact form (probe)...")
    msg = str(
        credentials.get("support_message")
        or "Nishcay AI automated support test — please disregard this message."
    ).strip()
    email_val = str(
        credentials.get("support_email") or credentials.get("email") or "support-test@example.com"
    ).strip()

    form = page.locator("form:has(textarea)").first
    if await form.count() == 0:
        form = page.locator("form:has(input[type='email'])").first

    if await form.count() == 0:
        actions.append({"flow": "support", "step": "contact_form", "ok": False, "skipped": True})
        await emit( "ℹ️ No obvious contact form on page")
        return

    try:
        ta = form.locator("textarea").first
        if await ta.count() and await ta.is_visible():
            await ta.fill(msg[:4000])
        em = form.locator("input[type='email'], input[name*='email']").first
        if await em.count() and await em.is_visible():
            await em.fill(email_val)
        for name in ("subject", "name", "topic"):
            inp = form.locator(f"input[name*='{name}'], input[id*='{name}']").first
            if await inp.count() and await inp.is_visible():
                await inp.fill(f"Automated test ({name})")
                break

        submitted = False
        for txt in ("Send", "Submit", "Send message"):
            try:
                await form.locator(f"button:has-text('{txt}')").first.click(timeout=8000)
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            try:
                await form.locator("input[type='submit']").first.click(timeout=8000)
                submitted = True
            except Exception:
                pass

        await asyncio.sleep(0.8)
        body = (await page.inner_text("body"))[:12_000].lower()
        success = any(
            x in body
            for x in (
                "thank",
                "received",
                "success",
                "sent",
                "submitted",
                "we got",
                "we'll be in touch",
            )
        )
        actions.append(
            {
                "flow": "support",
                "step": "contact_form",
                "ok": success or submitted,
                "submitted": submitted,
                "success_signal": success,
                "page_url": page.url,
            }
        )
        if submitted and not success:
            defects.append(
                _support_defect(
                    defect_id="form_submission_failed",
                    impact="Support",
                    description="Contact form submitted but no thank-you/success confirmation detected",
                    page_url=page.url,
                    severity="medium",
                )
            )
            await emit( "⚠️ Form submit without clear confirmation")
        elif submitted:
            await emit( "✅ Support form submitted with confirmation signal")
        else:
            defects.append(
                _support_defect(
                    defect_id="form_submission_failed",
                    impact="Support",
                    description="Could not submit support form (no working submit control)",
                    page_url=page.url,
                    severity="high",
                )
            )
            await emit( "⚠️ Could not submit contact form")
    except Exception as e:
        defects.append(
            _support_defect(
                defect_id="form_submission_failed",
                impact="Support",
                description=f"Support form error: {e!s}"[:4000],
                page_url=page.url,
                severity="high",
            )
        )
        actions.append({"flow": "support", "step": "contact_form", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Form probe failed: {e!s}")


async def _support_verify_contact_methods(
    page: Page,
    emit: Any,
    actions: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> None:
    await emit( "💬 Verifying contact methods (email, phone, social)...")
    try:
        info = await page.evaluate("""() => {
          const html = document.documentElement.innerHTML || '';
          const text = document.body.innerText || '';
          const mailto = (html.match(/mailto:[^\\s\"'<>]+/gi) || []).length;
          const tel = (html.match(/tel:[^\\s\"'<>]+/gi) || []).length;
          const emailText = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}/.test(text);
          const phoneText = /(\\+?\\d[\\d\\s().-]{8,}\\d)/.test(text);
          const social = ['facebook.com', 'twitter.com', 'x.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'tiktok.com', 'wa.me', 'whatsapp'].some(
            (d) => html.toLowerCase().includes(d)
          );
          return { mailto, tel, emailText, phoneText, social };
        }""")
        has_any = (
            info.get("mailto", 0) > 0
            or info.get("tel", 0) > 0
            or info.get("emailText")
            or info.get("phoneText")
            or info.get("social")
        )
        actions.append(
            {
                "flow": "support",
                "step": "contact_methods",
                "ok": bool(has_any),
                "detail": info,
                "page_url": page.url,
            }
        )
        if not has_any:
            defects.append(
                _support_defect(
                    defect_id="support_unreachable",
                    impact="Trust",
                    description="No mailto, tel:, obvious email/phone in text, or social profile links detected",
                    page_url=page.url,
                    severity="medium",
                )
            )
            await emit( "⚠️ No clear contact channels on page")
        else:
            await emit( "✅ At least one contact method detected")
    except Exception as e:
        actions.append({"flow": "support", "step": "contact_methods", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Contact method scan failed: {e!s}")


async def run_support_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Trust + support: help/FAQ, chat widget, contact form, contact channels."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "support", "step": "start", "page_url": page.url}]
    metrics: dict[str, Any] = {
        "help_page_ok": False,
        "chat_tested": False,
        "chat_ok": False,
        "form_submitted": False,
        "contact_methods_ok": False,
        "support_defects": 0,
    }

    await _browse_maybe_goto_start(page, credentials, emit, actions)

    try:
        metrics["help_page_ok"] = await _support_open_help_faq(
            page, credentials, emit, actions, defects
        )
    except Exception as e:
        logger.exception("support help page")
        await emit( f"❌ Help page step: {e!s}")
        defects.append(
            _support_defect(
                defect_id="support_unreachable",
                impact="Trust",
                description=str(e)[:4000],
                page_url=page.url,
                severity="high",
            )
        )

    if not metrics["help_page_ok"]:
        metrics["support_defects"] = len(defects)
        return _flow_result(defects=defects, actions=actions, metrics=metrics)

    try:
        await _support_test_live_chat(page, emit, actions, defects)
        metrics["chat_tested"] = True
        for a in reversed(actions):
            if a.get("step") == "live_chat":
                if a.get("skipped"):
                    metrics["chat_ok"] = bool(a.get("embedded_chat_iframe"))
                else:
                    metrics["chat_ok"] = bool(a.get("ok"))
                break
    except Exception as e:
        logger.exception("support chat")
        await emit( f"❌ Chat step: {e!s}")
        defects.append(
            _support_defect(
                defect_id="chat_not_working",
                impact="Support",
                description=str(e)[:4000],
                page_url=page.url,
                severity="high",
            )
        )

    try:
        await _support_submit_contact_form(page, credentials, emit, actions, defects)
        for a in reversed(actions):
            if a.get("step") == "contact_form":
                metrics["form_submitted"] = bool(a.get("submitted")) or bool(a.get("ok"))
                break
    except Exception as e:
        logger.exception("support form")
        await emit( f"❌ Form step: {e!s}")

    try:
        await _support_verify_contact_methods(page, emit, actions, defects)
        for a in reversed(actions):
            if a.get("step") == "contact_methods":
                metrics["contact_methods_ok"] = bool(a.get("ok"))
                break
    except Exception as e:
        logger.exception("support contact methods")
        await emit( f"❌ Contact methods: {e!s}")

    metrics["support_defects"] = len(defects)
    await emit( f"📊 Support flow complete — {len(defects)} defect(s)")

    return _flow_result(defects=defects, actions=actions, metrics=metrics)


# Single-page, no navigation: total wall time for all UI probes (see run_ui_integrity_scan).
_UI_INTEGRITY_MAX_SECONDS = 5.0


async def _ui_probe_broken_images(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> int:
    await emit( "🖼 UI: detecting broken images...")
    n = 0
    try:
        rows = await page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('img').forEach((img, i) => {
            const src = (img.getAttribute('src') || '').trim();
            if (!src && !img.src) {
              out.push({ index: i, reason: 'empty_src' });
              return;
            }
            const data = src.startsWith('data:');
            if (img.complete && img.naturalWidth === 0 && img.naturalHeight === 0 && !data) {
              out.push({ index: i, reason: 'zero_intrinsic', src: (src || img.src || '').slice(0, 160) });
            }
          });
          return out.slice(0, 30);
        }""")
        for row in rows:
            defects.append(
                _ui_defect(
                    defect_id="broken_images",
                    impact="Trust",
                    description=f"Image issue: {row!r}",
                    page_url=page.url,
                    severity="medium",
                )
            )
            n += 1
        actions.append({"flow": "ui", "step": "broken_images", "count": len(rows), "page_url": page.url})
    except Exception as e:
        actions.append({"flow": "ui", "step": "broken_images", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Broken image scan failed: {e!s}")
    return n


async def _ui_probe_cta_clickable(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> None:
    await emit( "🖼 UI: checking CTA buttons (disabled / unresponsive)...")
    try:
        cta_issues = await page.evaluate("""() => {
          const out = [];
          const re = /buy|shop|cart|checkout|order|subscribe|pay|add to|purchase|get started|donate|book/i;
          document.querySelectorAll('button, [role="button"], a[class*="btn"], a.button, a').forEach((el) => {
            const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
            if (!re.test(t) || t.length > 120) return;
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return;
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
              out.push({ text: t.slice(0, 100), reason: 'disabled' });
              return;
            }
            const st = window.getComputedStyle(el);
            if (st.pointerEvents === 'none' || st.cursor === 'not-allowed' || parseFloat(st.opacity) < 0.35) {
              out.push({
                text: t.slice(0, 100),
                reason: 'non_interactive_style',
                pointerEvents: st.pointerEvents,
                opacity: st.opacity,
              });
            }
          });
          return out.slice(0, 24);
        }""")
        for row in cta_issues:
            defects.append(
                _ui_defect(
                    defect_id="cta_not_clickable",
                    impact="Revenue",
                    description=f"CTA not usable: {row!r}",
                    page_url=page.url,
                    severity="high",
                )
            )
        actions.append(
            {
                "flow": "ui",
                "step": "cta_clickable",
                "issues": len(cta_issues),
                "page_url": page.url,
            }
        )
        await emit( f"🖼 CTA issues: {len(cta_issues)}")
    except Exception as e:
        actions.append({"flow": "ui", "step": "cta_clickable", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ CTA scan failed: {e!s}")


async def _ui_probe_console(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> int:
    await emit( "🖼 UI: capturing JS console errors...")
    buf: list[str] = []

    def _on_console(msg: Any) -> None:
        if getattr(msg, "type", None) == "error":
            buf.append(str(msg.text or ""))

    page.on("console", _on_console)
    n = 0
    try:
        await asyncio.sleep(0.12)
        extra = await capture_console_errors(page, emit, console_buffer=buf)
        for item in extra:
            defects.append(
                _ui_defect(
                    defect_id="console_errors",
                    impact="UX",
                    description=str(item.get("description") or item)[:4000],
                    page_url=page.url,
                    severity=str(item.get("severity") or "medium"),
                )
            )
            n += 1
        actions.append({"flow": "ui", "step": "console_errors", "count": n, "page_url": page.url})
        await emit( f"🖼 Console-related findings: {n}")
    except Exception as e:
        actions.append({"flow": "ui", "step": "console_errors", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Console capture failed: {e!s}")
    finally:
        try:
            page.remove_listener("console", _on_console)
        except Exception:
            pass
    return n


async def _ui_probe_load_time(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> float | None:
    await emit( "🖼 UI: measuring page load time...")
    load_ms: float | None = None
    try:
        timing = await page.evaluate("""() => {
          const nav = performance.getEntriesByType('navigation')[0];
          if (nav && nav.loadEventEnd && nav.fetchStart) {
            return { loadMs: nav.loadEventEnd - nav.fetchStart };
          }
          const p = performance.timing;
          if (p.loadEventEnd && p.navigationStart) {
            return { loadMs: p.loadEventEnd - p.navigationStart };
          }
          return { loadMs: null };
        }""")
        raw = timing.get("loadMs")
        load_ms = float(raw) if raw is not None else None
        actions.append({"flow": "ui", "step": "page_load_time", "load_ms": load_ms, "page_url": page.url})
        if load_ms is not None and load_ms > 3000:
            defects.append(
                _ui_defect(
                    defect_id="slow_page",
                    impact="Revenue",
                    description=f"Page load interval ~{int(load_ms)}ms exceeds 3000ms threshold",
                    page_url=page.url,
                    severity="high",
                )
            )
            await emit( f"⚠️ Slow page load: {int(load_ms)}ms")
        else:
            await emit( f"🖼 Load metric: {load_ms}ms" if load_ms is not None else "🖼 Load metric: n/a")
    except Exception as e:
        actions.append({"flow": "ui", "step": "page_load_time", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Load timing failed: {e!s}")
    return load_ms


async def _ui_probe_empty_blocks(
    page: Page, emit: Any, defects: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> int:
    await emit( "🖼 UI: detecting empty UI containers...")
    n = 0
    try:
        hollow = await page.evaluate("""() => {
          const out = [];
          const sel = 'main section, [class*="container"], [class*="wrapper"], [class*="grid"], [class*="content"]';
          document.querySelectorAll(sel).forEach((el) => {
            if (out.length >= 12) return;
            const r = el.getBoundingClientRect();
            if (r.width < 100 || r.height < 80) return;
            const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
            const hasMedia = el.querySelector('img, svg, video, iframe, canvas, table, form, ul, ol, article, picture');
            if (txt.length < 12 && !hasMedia) {
              const cls = (typeof el.className === 'string' ? el.className : '').slice(0, 100);
              out.push({ tag: el.tagName, className: cls });
            }
          });
          return out;
        }""")
        for row in hollow:
            defects.append(
                _ui_defect(
                    defect_id="empty_ui_blocks",
                    impact="UX",
                    description=f"Large container with little text and no obvious content widgets: {row!r}",
                    page_url=page.url,
                    severity="low",
                )
            )
            n += 1
        actions.append({"flow": "ui", "step": "empty_ui_blocks", "count": len(hollow), "page_url": page.url})
        await emit( f"🖼 Empty-ish blocks flagged: {len(hollow)}")
    except Exception as e:
        actions.append({"flow": "ui", "step": "empty_ui_blocks", "ok": False, "error": str(e)[:2000]})
        await emit( f"❌ Empty block scan failed: {e!s}")
    return n


async def run_ui_integrity_scan(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """
    Lightweight checks on the **current** page only (no link crawling, no extra navigation).
    Probes: broken images, disabled/unusable CTAs, console
    errors, load time, empty layout blocks. Hard budget: ``_UI_INTEGRITY_MAX_SECONDS`` per page.
    """
    _ = credentials
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "ui", "step": "start", "page_url": page.url}]

    deadline = time.monotonic() + _UI_INTEGRITY_MAX_SECONDS
    timed_out = False

    probe_steps: list[
        tuple[str, Callable[..., Awaitable[Any]]]
    ] = [
        ("broken_images", _ui_probe_broken_images),
        ("cta_clickable", _ui_probe_cta_clickable),
        ("console_errors", _ui_probe_console),
        ("load_time", _ui_probe_load_time),
        ("empty_blocks", _ui_probe_empty_blocks),
    ]

    for step_name, probe_fn in probe_steps:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            actions.append(
                {
                    "flow": "ui",
                    "step": step_name,
                    "skipped": True,
                    "reason": "budget_exhausted",
                    "page_url": page.url,
                }
            )
            await emit( f"⏱ UI integrity: budget exhausted before {step_name}")
            break
        try:
            await asyncio.wait_for(
                probe_fn(page, emit, defects, actions),
                timeout=max(0.05, remaining),
            )
        except asyncio.TimeoutError:
            timed_out = True
            actions.append(
                {
                    "flow": "ui",
                    "step": step_name,
                    "timeout": True,
                    "page_url": page.url,
                }
            )
            await emit(
                f"⏱ UI integrity: timed out at {step_name} (max {_UI_INTEGRITY_MAX_SECONDS:.0f}s per page)",
            )
            break
        except Exception as e:
            logger.exception("ui integrity step %s", step_name)
            await emit( f"❌ {step_name}: {e!s}")

    metrics = {
        "ui_defect_count": len(defects),
        "page_url": page.url,
        "defect_types": sorted({str(d.get("defect")) for d in defects if isinstance(d, dict)}),
        "ui_integrity_budget_seconds": _UI_INTEGRITY_MAX_SECONDS,
        "ui_integrity_timed_out": timed_out,
    }
    await emit( f"📊 UI integrity complete — {len(defects)} issue(s)")

    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def run_product_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Open multiple product detail pages and validate image / price / CTA signals."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "product", "step": "start", "page_url": page.url}]

    await _browse_maybe_goto_start(page, credentials, emit, actions)
    await emit("📦 Product flow: opening and validating product pages...")

    try:
        hrefs = await page.evaluate("""() => {
          const sels = [
            'a[href*="/product"]', 'a[href*="/products"]', 'a[href*="/item"]', 'a[href*="/p/"]',
            '[data-product-url]', '.product a[href]', '[class*="product-card" i] a',
          ];
          const seen = new Set();
          const out = [];
          for (const s of sels) {
            try {
              document.querySelectorAll(s).forEach((a) => {
                const h = (a.href || '').trim();
                if (h && h.length > 8 && !seen.has(h)) { seen.add(h); out.push(h); }
              });
            } catch (e) {}
          }
          return out.slice(0, 5);
        }""")
    except Exception as e:
        await emit(f"❌ Product link discovery failed: {e!s}")
        hrefs = []

    if not hrefs:
        defects.append(
            _browse_defect(
                defect_id="product_page_incomplete",
                impact="Revenue",
                description="No product links found for product flow",
                page_url=page.url,
                severity="high",
            )
        )
        await emit("⚠️ No product links found")
        return _flow_result(
            defects=defects,
            actions=actions,
            metrics={"product_defects": len(defects), "pdps_opened": 0},
        )

    start_url = page.url
    pdps_opened = 0
    for href in (hrefs or [])[:3]:
        try:
            await page.goto(str(href), wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(0.35)
            pdps_opened += 1
        except Exception as e:
            defects.append(
                _browse_defect(
                    defect_id="broken_navigation",
                    impact="UX",
                    description=f"Could not open product URL: {e!s}"[:4000],
                    page_url=start_url,
                    severity="medium",
                )
            )
            actions.append({"flow": "product", "step": "pdp_open", "ok": False, "href": str(href)[:500]})
            continue

        chk = await page.evaluate("""() => {
          const body = (document.body.innerText || '').toLowerCase();
          const priceRe = /(\\$|€|£|₹|usd|eur|gbp|rs\\.?\\s*\\d|\\d+\\.\\d{2}\\s*(usd|eur)?)/i;
          const imgs = Array.from(document.querySelectorAll('img')).filter((img) => {
            const r = img.getBoundingClientRect();
            return r.width >= 80 && r.height >= 80 && (img.complete ? img.naturalWidth > 0 : true);
          });
          const cartBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).some((el) => {
            const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
            return /add to cart|add to bag|buy now|purchase/.test(t);
          });
          return {
            image_ok: imgs.length > 0,
            image_count: imgs.length,
            price_ok: priceRe.test(body) || !!document.querySelector('[class*="price" i], [itemprop="price"]'),
            add_to_cart: cartBtn,
          };
        }""")

        actions.append(
            {
                "flow": "product",
                "step": "pdp_validation",
                "ok": True,
                "pdp_url": page.url,
                "checks": chk,
            }
        )
        missing: list[str] = []
        if not chk.get("image_ok"):
            missing.append("images")
        if not chk.get("price_ok"):
            missing.append("price")
        if not chk.get("add_to_cart"):
            missing.append("add_to_cart")
        if missing:
            defects.append(
                _browse_defect(
                    defect_id="product_page_incomplete",
                    impact="Revenue",
                    description=f"Product page missing expected elements: {', '.join(missing)}",
                    page_url=page.url,
                    severity="high",
                )
            )
            await emit(f"⚠️ PDP incomplete: {missing}")
        else:
            await emit("✅ PDP shows image(s), price signal, and add-to-cart CTA")

    metrics = {
        "product_defects": len(defects),
        "pdps_opened": pdps_opened,
        "defect_types": sorted({str(d.get("defect")) for d in defects if isinstance(d, dict)}),
    }
    await emit(f"📊 Product flow complete — {len(defects)} defect(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def _footer_links_probe(
    page: Page,
    emit: Any,
    defects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    flow_key: str = "navigation",
) -> None:
    await emit("🧭 Navigation: sampling footer links...")
    start_url = page.url
    try:
        links = await page.evaluate("""() => {
          const root = document.querySelector('footer, [role="contentinfo"]') || document.body;
          const out = [];
          root.querySelectorAll('a[href]').forEach((a) => {
            const h = (a.getAttribute('href') || '').trim();
            const t = (a.innerText || a.getAttribute('aria-label') || '').trim();
            if (!h || h === '#' || h.toLowerCase().startsWith('javascript:')) return;
            if (t.length < 2 || t.length > 120) return;
            out.push({ href: a.href, text: t.slice(0, 80) });
          });
          return out.slice(0, 8);
        }""")
    except Exception as e:
        await emit(f"❌ Footer link discovery failed: {e!s}")
        actions.append({"flow": flow_key, "step": "footer_links", "ok": False, "error": str(e)[:2000]})
        return

    if not links:
        await emit("ℹ️ No footer links collected")
        actions.append({"flow": flow_key, "step": "footer_links", "ok": True, "clicks": 0})
        return

    max_clicks = min(4, len(links))
    broken = 0
    for i in range(max_clicks):
        item = links[i]
        href = str(item.get("href") or "")
        text = str(item.get("text") or "")
        try:
            await emit(f"🧭 Footer click [{i + 1}/{max_clicks}]: {text[:50]}")
            await page.goto(href, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(0.2)
            bad = await _page_signals_not_found_or_error(page)
            if bad:
                broken += 1
                defects.append(
                    _browse_defect(
                        defect_id="broken_navigation",
                        impact="UX",
                        description=f"Footer link may be broken or error page: {text[:100]}",
                        page_url=page.url,
                        severity="medium",
                    )
                )
            actions.append(
                {
                    "flow": flow_key,
                    "step": "footer_navigation",
                    "ok": not bad,
                    "index": i,
                    "link_text": text[:200],
                    "result_url": page.url,
                }
            )
        except Exception as e:
            broken += 1
            defects.append(
                _browse_defect(
                    defect_id="broken_navigation",
                    impact="UX",
                    description=f"Footer navigation failed: {text[:60]} — {e!s}"[:4000],
                    page_url=start_url,
                    severity="medium",
                )
            )
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=25_000)
            await asyncio.sleep(0.15)
        except Exception:
            pass

    await emit(f"🧭 Footer link pass complete — {broken} broken signal(s)")


async def run_navigation_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Header navigation, footer links, dead / error page detection."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "navigation", "step": "start", "page_url": page.url}]

    await _browse_maybe_goto_start(page, credentials, emit, actions)
    try:
        await _browse_nav_probe(page, emit, defects, actions, flow_key="navigation")
    except Exception as e:
        logger.exception("navigation header")
        await emit(f"❌ Header navigation crashed: {e!s}")

    try:
        await _footer_links_probe(page, emit, defects, actions, flow_key="navigation")
    except Exception as e:
        logger.exception("navigation footer")
        await emit(f"❌ Footer navigation crashed: {e!s}")

    dead_href = await _broken_href_candidates(
        page,
        label="navigation_dead_link",
        text_needles=("home", "shop", "cart", "contact", "about"),
        href_needles=("/cart", "/product", "/contact", "/about"),
    )
    defects.extend(dead_href)
    if dead_href:
        actions.append(
            {
                "flow": "navigation",
                "step": "dead_href_scan",
                "ok": False,
                "candidates": len(dead_href),
                "page_url": page.url,
            }
        )
        await emit(f"⚠️ Found {len(dead_href)} suspicious empty/javascript links")

    metrics = {
        "navigation_defects": len(defects),
        "defect_types": sorted({str(d.get("defect")) for d in defects if isinstance(d, dict)}),
    }
    await emit(f"📊 Navigation flow complete — {len(defects)} defect(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def run_search_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Dedicated search journey: valid query, invalid query, results validation."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "search", "step": "start", "page_url": page.url}]

    await _browse_maybe_goto_start(page, credentials, emit, actions)
    await emit("🔎 Search flow: valid and invalid queries...")

    try:
        await _browse_search_probe(page, credentials, emit, defects, actions, valid=True, flow_key="search")
    except Exception as e:
        logger.exception("search valid")
        await emit(f"❌ Valid search crashed: {e!s}")

    try:
        await _browse_search_probe(page, credentials, emit, defects, actions, valid=False, flow_key="search")
    except Exception as e:
        logger.exception("search invalid")
        await emit(f"❌ Invalid search crashed: {e!s}")

    metrics = {
        "search_defects": len(defects),
        "defect_types": sorted({str(d.get("defect")) for d in defects if isinstance(d, dict)}),
    }
    await emit(f"📊 Search flow complete — {len(defects)} defect(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)


async def run_coupon_flow(
    page: Page,
    credentials: dict[str, Any],
    emit: Any,
) -> EcommerceFlowResult:
    """Apply a coupon / promo code and validate discount feedback or error messaging."""
    defects: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = [{"flow": "coupon", "step": "start", "page_url": page.url}]
    metrics: dict[str, Any] = {
        "coupon_applied_or_error": False,
        "coupon_defects": 0,
    }

    await _browse_maybe_goto_start(page, credentials, emit, actions)
    await emit("🎟 Coupon flow: locating cart / checkout and testing promo code...")

    base = str(credentials.get("target_url") or credentials.get("browse_start_url") or page.url).strip()
    cart_paths = ("/cart", "/view_cart", "/basket", "/checkout/cart")
    opened_cart = False
    for path in cart_paths:
        if opened_cart:
            break
        try:
            u = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
            await page.goto(u, wait_until="domcontentloaded", timeout=18_000)
            await asyncio.sleep(0.35)
            if not await _page_signals_not_found_or_error(page):
                opened_cart = True
                actions.append({"flow": "coupon", "step": "open_cart", "ok": True, "url": page.url})
                await emit(f"✅ Opened cart-like URL: {page.url[:100]}")
                break
        except Exception:
            continue

    if not opened_cart:
        for sel in ("a[href*='cart']", "a[href*='view_cart']", "button:has-text('Cart')"):
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible(timeout=2000):
                    await loc.click(timeout=8000)
                    await asyncio.sleep(0.5)
                    opened_cart = True
                    actions.append({"flow": "coupon", "step": "open_cart", "ok": True, "via": sel})
                    await emit("✅ Opened cart via UI control")
                    break
            except Exception:
                continue

    promo_code = str(
        credentials.get("promo_code") or credentials.get("coupon_code") or "INVALID_NISHCAY_TEST"
    ).strip()

    promo_inputs = [
        "input[name*='discount']",
        "input[name*='coupon']",
        "input[name*='promo']",
        "input[placeholder*='promo' i]",
        "input[placeholder*='coupon' i]",
        "input[id*='discount']",
    ]
    filled = False
    for pis in promo_inputs:
        try:
            pi = page.locator(pis).first
            if await pi.count() == 0 or not await pi.is_visible():
                continue
            await pi.fill(promo_code)
            filled = True
            break
        except Exception:
            continue

    if not filled:
        defects.append(
            _cart_defect(
                defect_id="pricing_not_updated",
                impact="Revenue",
                description="No promo/coupon input found on cart or checkout page",
                page_url=page.url,
            )
        )
        actions.append({"flow": "coupon", "step": "promo_apply", "ok": False, "skipped": True})
        await emit("⚠️ No coupon field found")
    else:
        applied = False
        for btxt in ("Apply", "Redeem", "Add", "Submit", "Apply Coupon"):
            try:
                await page.locator(f"button:has-text('{btxt}')").first.click(timeout=5000)
                applied = True
                break
            except Exception:
                continue
        await asyncio.sleep(0.65)
        body = (await page.inner_text("body"))[:8000].lower()
        discount_ok = any(
            x in body
            for x in (
                "discount",
                "promo",
                "applied",
                "invalid",
                "expired",
                "not valid",
                "error",
                "unable",
            )
        )
        metrics["coupon_applied_or_error"] = discount_ok
        actions.append(
            {
                "flow": "coupon",
                "step": "promo_apply",
                "ok": discount_ok,
                "code_used": promo_code[:80],
                "page_url": page.url,
            }
        )
        if not discount_ok:
            defects.append(
                _cart_defect(
                    defect_id="pricing_not_updated",
                    impact="Revenue",
                    description="Promo submit did not show recognizable discount, error, or feedback",
                    page_url=page.url,
                )
            )
            await emit("⚠️ Coupon response unclear")
        else:
            await emit("✅ Coupon field produced discount or error feedback")

    metrics["coupon_defects"] = len(defects)
    await emit(f"📊 Coupon flow complete — {len(defects)} defect(s)")
    return _flow_result(defects=defects, actions=actions, metrics=metrics)


ECOMMERCE_FLOWS: dict[str, Callable[..., Awaitable[EcommerceFlowResult]]] = {
    "auth": run_auth_flow,
    "browse": run_browse_flow,
    "cart": run_cart_flow,
    "checkout": run_checkout_flow,
    "support": run_support_flow,
    "ui": run_ui_integrity_scan,
    "product": run_product_flow,
    "navigation": run_navigation_flow,
    "search": run_search_flow,
    "coupon": run_coupon_flow,
}

def expand_selected_flows(items: list[Any]) -> list[str]:
    """
    Map task tokens to ordered micro task names (task groups + legacy flow aliases).
    Delegates to backend.core.task_registry.expand_task_selection.
    """
    from backend.core.task_registry import expand_task_selection

    toks: list[str] = []
    for raw in items or []:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if s:
            toks.append(s)
    return expand_task_selection(toks)


MICRO_TASK_TIMEOUT_SECONDS = 18.0

_MICRO_TASK_ALIASES: dict[str, str] = {
    "search": "search_product",
    "product": "open_product_from_search",
    "open_product": "open_product_from_search",
    "cart": "add_to_cart",
    "coupon": "apply_coupon",
    "checkout": "start_checkout",
    "support": "contact_support",
}


async def run_micro_task(
    page: Page,
    task: Any,
    context: dict[str, Any] | None,
    emit_event=None,
    *,
    timeout_seconds: float | None = None,
) -> EcommerceFlowResult:
    """
    Run one registered micro task (TASK_REGISTRY) with a strict wall-time limit.
    """
    from backend.core.context import create_context, ensure_shared_context
    from backend.core.micro_tasks import run_task
    from backend.core.task_registry import TASK_REGISTRY

    emit = make_safe_emitter(emit_event)
    raw = str(task or "").strip().lower().replace("-", "_")
    key = _MICRO_TASK_ALIASES.get(raw, raw)
    if key not in TASK_REGISTRY:
        await emit("⚡ Running task: UNKNOWN")
        return _flow_result(
            defects=[
                {
                    "defect": "unknown_micro_task",
                    "type": "micro_task",
                    "severity": "high",
                    "page_url": getattr(page, "url", "") or "",
                    "description": f"Unknown micro task: {task!r}",
                }
            ],
            actions=[{"flow": "micro", "step": "validate", "ok": False, "task": str(task)}],
            metrics={"micro_error": "unknown_task", "task": str(task)},
        )

    label = key.upper()
    await emit(f"⚡ Running task: {label}")
    task_fn = TASK_REGISTRY[key]
    to = float(timeout_seconds if timeout_seconds is not None else MICRO_TASK_TIMEOUT_SECONDS)
    ctx = ensure_shared_context(context or create_context())
    mr = await run_task(task_fn, page, ctx, emit, timeout=to)
    defects = list(mr.get("defects") or [])
    return _flow_result(
        defects=defects,
        actions=[{"flow": "micro", "task": key, "success": mr.get("success"), "impact": mr.get("impact")}],
        metrics={"micro_task": key, "result": mr},
    )


async def run_ecommerce_scan(
    page: Page,
    selected_flows: list[Any],
    context: dict[str, Any] | None,
    emit_event=None,
) -> dict[str, Any]:
    """
    Run **micro tasks only** (no crawler dependency): ``task → action → result`` via
    :func:`run_micro_task_group_scan`.

    ``selected_flows`` are group/task tokens expanded by ``expand_task_selection``.
    Unknown tokens are skipped. A failure in one task is isolated.
    Wall time capped at 90s by default (see micro_task_runner).
    """
    from backend.core.micro_task_runner import run_micro_task_group_scan

    toks: list[str] = []
    for raw in selected_flows or []:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if s:
            toks.append(s)
    return await run_micro_task_group_scan(page, toks, context, emit_event, budget_seconds=90.0)
