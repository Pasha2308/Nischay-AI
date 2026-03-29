"""
Micro Task Engine — independent e-commerce QA tasks with structured results.

Each task: async def task_*(page, context, emit) -> {task, success, defects, impact}
Shared context: use backend.core.context.create_context() (or pass a dict); ensure_shared_context()
merges default keys so tasks stay standalone. open_product_from_search sets selected_product;
add_to_cart increments cart_items on success; run_task records failures in last_errors.
Interactions use safe_click / safe_fill from ecommerce_plan only; pattern lists avoid brittle single selectors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from playwright.async_api import Page

from backend.core.context import ensure_shared_context
from backend.core.synthetic_data import generate_coupon, generate_search_query, generate_user_profile
from backend.core.ecommerce_plan import (
    _checkout_shipping_fixture,
    _credential_username_password,
    _first_matching_visible_selector,
    safe_click,
    safe_fill,
)

logger = logging.getLogger(__name__)

_LAST_ERRORS_CAP = 24


def _append_last_error(context: dict[str, Any], task_id: str, defects: list[dict[str, Any]]) -> None:
    if not defects:
        return
    le = context.setdefault("last_errors", [])
    if not isinstance(le, list):
        context["last_errors"] = []
        le = context["last_errors"]
    d0 = defects[0]
    le.append(
        {
            "task": task_id,
            "defect": d0.get("defect", ""),
            "description": (d0.get("description") or "")[:400],
        }
    )
    while len(le) > _LAST_ERRORS_CAP:
        le.pop(0)

EmitFn = Callable[[str], Awaitable[None]]
MicroTaskResult = dict[str, Any]

# --- Flexible selector / pattern groups (iterate — no single fixed site-specific selector) ---

SEARCH_INPUT_PATTERNS: list[str] = [
    "input[type='search']",
    "input[role='searchbox']",
    "input[name*='search' i]",
    "input[id*='search' i]",
    "input[placeholder*='search' i]",
    "input[aria-label*='search' i]",
    "form[action*='search' i] input[type='text']",
    "header input[type='text']",
]

SEARCH_SUBMIT_PATTERNS: list[str] = [
    "button[type='submit']",
    "input[type='submit']",
    "button[aria-label*='search' i]",
    "button[title*='search' i]",
    "[role='button'][aria-label*='search' i]",
    "button:has-text('Search')",
    "button:has-text('Go')",
    "button:has-text('Find')",
]

PRODUCT_RESULT_LINK_PATTERNS: list[str] = [
    "main a[href*='product']",
    "[role='main'] a[href*='product']",
    "[class*='search'] a[href]",
    "[class*='result'] a[href]",
    "ul[class*='product'] a[href]",
    "article a[href*='item']",
    "a[href*='/p/']",
    "a[href*='/product']",
]

PDP_HINT_PATTERNS: list[str] = [
    "button[aria-label*='cart' i]",
    "button[aria-label*='add' i]",
    "[itemprop='price']",
    "[data-price]",
    "input[name*='qty' i]",
]

ADD_TO_CART_PATTERNS: list[str] = [
    "button[aria-label*='cart' i]",
    "button[aria-label*='Add' i]",
    "button:has-text('Add to cart')",
    "button:has-text('Add to Cart')",
    "input[type='submit'][value*='cart' i]",
    "button[id*='AddToCart' i]",
    "button[name*='add-to-cart' i]",
    "[data-add-to-cart]",
]

COUPON_FIELD_PATTERNS: list[str] = [
    "input[name*='coupon' i]",
    "input[id*='coupon' i]",
    "input[placeholder*='coupon' i]",
    "input[name*='promo' i]",
    "input[placeholder*='promo' i]",
]

COUPON_APPLY_PATTERNS: list[str] = [
    "button:has-text('Apply')",
    "button:has-text('Add')",
    "input[type='submit'][value*='Apply' i]",
    "button[aria-label*='apply' i]",
]

CHECKOUT_CTA_PATTERNS: list[str] = [
    "a[href*='checkout' i]",
    "button:has-text('Checkout')",
    "a:has-text('Checkout')",
    "button:has-text('Proceed to checkout')",
    "a:has-text('Proceed to checkout')",
    "[data-checkout]",
    "button[aria-label*='checkout' i]",
]

ADDRESS_NAME_PATTERNS: list[str] = [
    "input[name*='full' i][name*='name' i]",
    "input[autocomplete='name']",
    "input[name*='first' i]",
    "input[placeholder*='name' i]",
]

ADDRESS_LINE_PATTERNS: list[str] = [
    "input[autocomplete='address-line1']",
    "input[name*='address' i]:not([name*='email' i])",
    "input[name*='street' i]",
    "input[placeholder*='address' i]",
]

PHONE_FIELD_PATTERNS: list[str] = [
    "input[type='tel']",
    "input[autocomplete='tel']",
    "input[name*='phone' i]",
]

FORM_CONTINUE_PATTERNS: list[str] = [
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button:has-text('Save')",
    "button[type='submit']",
    "input[type='submit']",
]

PLACE_ORDER_PATTERNS: list[str] = [
    "button:has-text('Place order')",
    "button:has-text('Place Order')",
    "button:has-text('Pay now')",
    "button:has-text('Complete order')",
    "button:has-text('Submit order')",
    "input[type='submit'][value*='Place' i]",
    "button[aria-label*='place order' i]",
]

TERMS_CHECKBOX_PATTERNS: list[str] = [
    "input[type='checkbox'][name*='terms' i]",
    "input[type='checkbox'][id*='terms' i]",
    "label:has-text('agree') input[type='checkbox']",
]

CONTACT_EMAIL_PATTERNS: list[str] = [
    "form input[type='email']",
    "input[type='email']",
    "input[name*='email' i]",
]

CONTACT_MESSAGE_PATTERNS: list[str] = [
    "textarea[name*='message' i]",
    "textarea[placeholder*='message' i]",
    "textarea",
]

CONTACT_SUBMIT_PATTERNS: list[str] = [
    "form button[type='submit']",
    "button:has-text('Send')",
    "button:has-text('Submit')",
    "input[type='submit']",
]

NAV_LINK_PATTERNS: list[str] = [
    "header nav a[href]",
    "nav[aria-label*='main' i] a[href]",
    "[role='navigation'] a[href]",
    "nav a[href]",
]


def _task_id(name: str) -> str:
    return name if not name.startswith("task_") else name.replace("task_", "", 1)


def _result(
    task: str,
    success: bool,
    defects: list[dict[str, Any]],
    impact: str,
) -> MicroTaskResult:
    return {
        "task": task,
        "success": bool(success),
        "defects": defects,
        "impact": impact if impact in ("LOW", "MEDIUM", "HIGH") else "MEDIUM",
    }


async def _emit_safe(emit: EmitFn, message: str) -> None:
    try:
        await emit(message)
    except Exception as e:
        logger.debug("emit failed: %s", e)


async def _snapshot_page_signals(page: Page) -> dict[str, Any]:
    try:
        url = page.url or ""
        cart_hint = await page.evaluate("""() => {
          const t = document.body ? document.body.innerText.slice(0, 5000) : '';
          const m = t.match(/cart|bag|basket/gi);
          return { textLen: t.length, cartMentions: m ? m.length : 0 };
        }""")
        n_products = await page.locator(
            "a[href*='product'], [data-product-id], [class*='product'] a[href]"
        ).count()
        return {"url": url, **cart_hint, "productLinks": n_products}
    except Exception as e:
        logger.debug("snapshot: %s", e)
        try:
            u = page.url or ""
        except Exception:
            u = ""
        return {"url": u, "textLen": 0, "cartMentions": 0, "productLinks": 0}


def _pick_impact(success: bool, defects: list[dict[str, Any]]) -> str:
    if not success:
        return "HIGH"
    sev = [str(d.get("severity", "")).lower() for d in defects]
    if "high" in sev:
        return "HIGH"
    if defects:
        return "MEDIUM"
    return "LOW"


def _default_search_keyword(context: dict[str, Any]) -> str:
    q = str(context.get("search_query") or context.get("query") or "").strip()
    if q:
        return q
    return generate_search_query()


async def _body_text_lower(page: Page, limit: int = 8000) -> str:
    try:
        t = await page.inner_text("body", timeout=5000)
        return (t or "")[:limit].lower()
    except Exception:
        return ""


async def _has_empty_results_signal(page: Page) -> bool:
    text = await _body_text_lower(page, 4000)
    needles = (
        "no results",
        "no products",
        "nothing found",
        "0 results",
        "did not match",
        "no items",
        "we couldn't find",
    )
    return any(n in text for n in needles)


async def _has_plausible_search_results(page: Page) -> bool:
    try:
        n = await page.locator(
            "a[href*='product'], [data-product-id], [class*='product-tile'], article[class*='product']"
        ).count()
        if n >= 1:
            return True
    except Exception:
        pass
    if await _has_empty_results_signal(page):
        return False
    snap = await _snapshot_page_signals(page)
    return int(snap.get("productLinks", 0)) >= 1


async def _submit_search_safe_click_only(page: Page, emit: EmitFn, tid: str) -> bool:
    for sel in SEARCH_SUBMIT_PATTERNS:
        await _emit_safe(emit, f"[micro:{tid}] try search submit pattern")
        if await safe_click(page, sel, timeout_ms=5000):
            return True
    return False


async def _detect_validation_blockers(page: Page) -> bool:
    text = await _body_text_lower(page, 6000)
    form_err = await page.locator(
        "[aria-invalid='true'], [role='alert'], .error:visible, .field-error:visible, .invalid:visible"
    ).count()
    keywords = ("required", "invalid", "must enter", "please enter", "error", "fix")
    return form_err > 0 or any(k in text for k in keywords)


async def run_task(
    task_fn: Callable[..., Awaitable[MicroTaskResult]],
    page: Page,
    context: dict[str, Any],
    emit: EmitFn,
    *,
    timeout: float = 20,
) -> MicroTaskResult:
    key = _task_id(getattr(task_fn, "__name__", "unknown"))
    context = ensure_shared_context(context)
    await _emit_safe(emit, f"[micro:{key}] ▶ run_task start (timeout={timeout}s)")
    try:
        out = await asyncio.wait_for(task_fn(page, context, emit), timeout=timeout)
        await _emit_safe(emit, f"[micro:{key}] ▶ run_task finished success={out.get('success')}")
        if isinstance(out, dict) and not out.get("success"):
            _append_last_error(context, str(out.get("task", key)), list(out.get("defects") or []))
        if isinstance(out, dict) and "task" in out and "success" in out and "defects" in out and "impact" in out:
            return out
        await _emit_safe(emit, f"[micro:{key}] ⚠ invalid task return shape; coercing failure")
        inv = [{"defect": "invalid_task_output", "description": "Task did not return full structure", "severity": "high", "page_url": page.url}]
        _append_last_error(context, key, inv)
        return _result(key, False, inv, "HIGH")
    except asyncio.TimeoutError:
        await _emit_safe(emit, f"[micro:{key}] ⏱ task exceeded {timeout}s")
        td = [{"defect": "task_timeout", "description": f"Exceeded {timeout}s", "severity": "high", "page_url": page.url}]
        _append_last_error(context, key, td)
        return _result(key, False, td, "HIGH")
    except Exception as e:
        logger.exception("run_task: %s", key)
        await _emit_safe(emit, f"[micro:{key}] ❌ exception: {str(e)[:200]}")
        ed = [{"defect": "task_exception", "description": str(e)[:500], "severity": "high", "page_url": page.url}]
        _append_last_error(context, key, ed)
        return _result(key, False, ed, "HIGH")


# --- Tasks ---


async def task_login_user(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "login_user"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — login")

    user, pwd = _credential_username_password(context)
    if not user or not pwd:
        defects.append(
            {
                "defect": "login_missing_credentials",
                "description": "username/password not in context",
                "severity": "medium",
                "page_url": page.url,
            }
        )
        await _emit_safe(emit, f"[micro:{tid}] after — missing credentials")
        return _result(tid, False, defects, "MEDIUM")

    login_url = (context.get("login_url") or context.get("target_url") or "").strip()
    if login_url:
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=12_000)
            await page.wait_for_timeout(400)
        except Exception as e:
            defects.append(
                {
                    "defect": "login_nav_failed",
                    "description": str(e)[:300],
                    "severity": "high",
                    "page_url": page.url,
                }
            )

    before = await _snapshot_page_signals(page)
    u_sel = await _first_matching_visible_selector(
        page,
        [
            "input[type='email']",
            "input[name*='email' i]",
            "input[autocomplete='username']",
            "input[type='text']",
        ],
    )
    p_sel = await _first_matching_visible_selector(page, ["input[type='password']"])
    if not u_sel or not p_sel:
        defects.append(
            {
                "defect": "login_fields_not_found",
                "description": "No visible login fields",
                "severity": "high",
                "page_url": page.url,
            }
        )
        await _emit_safe(emit, f"[micro:{tid}] after — no fields")
        return _result(tid, False, defects, _pick_impact(False, defects))

    if not await safe_fill(page, u_sel, user, timeout_ms=5000):
        defects.append({"defect": "login_fill_user", "description": "safe_fill user failed", "severity": "high", "page_url": page.url})
    if not await safe_fill(page, p_sel, pwd, timeout_ms=5000):
        defects.append({"defect": "login_fill_pass", "description": "safe_fill password failed", "severity": "high", "page_url": page.url})

    sub_sel = await _first_matching_visible_selector(
        page,
        [
            "button[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Sign in')",
            "input[type='submit']",
        ],
    )
    if not sub_sel or not await safe_click(page, sub_sel, timeout_ms=8000):
        defects.append({"defect": "login_submit", "description": "Login submit failed", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — submit failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1200)
    after = await _snapshot_page_signals(page)
    ui_changed = (
        before.get("url") != after.get("url")
        or await page.locator("input[type='password']").count() == 0
        or abs(int(after.get("textLen", 0)) - int(before.get("textLen", 0))) > 80
    )
    if not ui_changed:
        defects.append(
            {
                "defect": "login_no_ui_change",
                "description": "No clear login outcome",
                "severity": "high",
                "page_url": page.url,
            }
        )

    ok = len(defects) == 0
    if ok:
        context["login_state"] = True
        await _emit_safe(emit, f"[micro:{tid}] context.login_state=True")
    await _emit_safe(emit, f"[micro:{tid}] after — ok={ok}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_search_product(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "search_product"
    defects: list[dict[str, Any]] = []
    if not str(context.get("search_query") or context.get("query") or "").strip():
        await _emit_safe(emit, "Using synthetic user data")
    kw = _default_search_keyword(context)
    await _emit_safe(emit, f"[micro:{tid}] before — search keyword={kw!r}")

    before = await _snapshot_page_signals(page)
    search_sel = await _first_matching_visible_selector(page, SEARCH_INPUT_PATTERNS)
    if not search_sel:
        defects.append({"defect": "search_input_missing", "description": "No search input matched", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no search input")
        return _result(tid, False, defects, "HIGH")

    if not await safe_fill(page, search_sel, kw, timeout_ms=5000):
        defects.append({"defect": "search_not_working", "description": "safe_fill search failed", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — fill failed")
        return _result(tid, False, defects, "HIGH")

    submitted = await _submit_search_safe_click_only(page, emit, tid)
    if not submitted:
        defects.append({"defect": "search_not_working", "description": "Could not submit search via safe_click", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — submit failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1000)

    after = await _snapshot_page_signals(page)
    ui_moved = (
        before.get("url") != after.get("url")
        or abs(int(after.get("textLen", 0)) - int(before.get("textLen", 0))) > 80
        or int(after.get("productLinks", 0)) != int(before.get("productLinks", 0))
    )
    if not ui_moved:
        defects.append({"defect": "search_not_working", "description": "No meaningful UI change after search", "severity": "high", "page_url": page.url})

    empty_state = await _has_empty_results_signal(page)
    if empty_state:
        defects.append({"defect": "no_results", "description": "Empty / no-results state shown", "severity": "high", "page_url": page.url})

    has_results = await _has_plausible_search_results(page)
    if not has_results and not empty_state:
        defects.append({"defect": "no_results", "description": "No product listing or clear empty-state after search", "severity": "high", "page_url": page.url})

    high = [d for d in defects if d.get("severity") == "high"]
    ok = not high and has_results and not empty_state
    await _emit_safe(emit, f"[micro:{tid}] after — results={has_results} defects={len(defects)}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_open_product_from_search(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "open_product_from_search"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — open first result")

    url_before = page.url or ""
    before = await _snapshot_page_signals(page)

    clicked = False
    for sel in PRODUCT_RESULT_LINK_PATTERNS:
        try:
            loc = page.locator(sel)
            if await loc.count() == 0:
                continue
            if await safe_click(page, sel, timeout_ms=7000, nth=0):
                clicked = True
                await _emit_safe(emit, f"[micro:{tid}] clicked result via pattern")
                break
        except Exception as e:
            logger.debug("open_product %s: %s", sel, e)

    if not clicked:
        defects.append({"defect": "product_click_failed", "description": "Could not click a product link from results", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — click failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1200)
    url_after = page.url or ""
    if url_before == url_after:
        defects.append({"defect": "page_not_changed", "description": "URL unchanged after product click", "severity": "high", "page_url": page.url})

    pdp_signal = False
    for hint in PDP_HINT_PATTERNS:
        try:
            if await page.locator(hint).count() > 0:
                pdp_signal = True
                break
        except Exception:
            continue
    if not pdp_signal:
        text_delta = abs((await _snapshot_page_signals(page)).get("textLen", 0) - before.get("textLen", 0))
        pdp_signal = text_delta > 150 and url_before != url_after

    if not pdp_signal:
        defects.append({"defect": "pdp_not_loaded", "description": "No clear product-page signals after click", "severity": "high", "page_url": page.url})

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0
    if ok:
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        context["selected_product"] = {"url": page.url or "", "title": title}
        await _emit_safe(emit, f"[micro:{tid}] context.selected_product set")
    await _emit_safe(emit, f"[micro:{tid}] after — ok={ok}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_add_to_cart(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "add_to_cart"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — add to cart")

    before = await _snapshot_page_signals(page)
    atc_sel = await _first_matching_visible_selector(page, ADD_TO_CART_PATTERNS)
    if not atc_sel:
        defects.append({"defect": "add_to_cart_missing", "description": "No add-to-cart control matched", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no button")
        return _result(tid, False, defects, "HIGH")

    if not await safe_click(page, atc_sel, timeout_ms=8000):
        defects.append({"defect": "add_to_cart_not_clickable", "description": "safe_click add-to-cart failed", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — not clickable")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1100)
    after = await _snapshot_page_signals(page)

    badge = await page.locator("[class*='cart-count'], [data-cart-count], [data-count], .cart-badge, header [aria-live]").count()
    popup = await page.locator("[role='dialog']:visible, [role='alert']:visible, [class*='toast']:visible, [class*='notification']:visible").count()
    mentions_delta = int(after.get("cartMentions", 0)) - int(before.get("cartMentions", 0))
    text_delta = abs(int(after.get("textLen", 0)) - int(before.get("textLen", 0)))
    cart_updated = badge > 0 or popup > 0 or mentions_delta != 0 or text_delta > 80 or before.get("url") != after.get("url")

    if not cart_updated:
        defects.append({"defect": "cart_not_updated", "description": "No badge, popup, cart text change, or URL change after add-to-cart", "severity": "high", "page_url": page.url})

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0
    if ok and cart_updated:
        try:
            prev = int(context.get("cart_items", 0))
        except (TypeError, ValueError):
            prev = 0
        context["cart_items"] = prev + 1
        await _emit_safe(emit, f"[micro:{tid}] context.cart_items={context['cart_items']}")

    await _emit_safe(emit, f"[micro:{tid}] after — cart_updated={cart_updated}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_apply_coupon(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "apply_coupon"
    defects: list[dict[str, Any]] = []
    code = str(context.get("coupon_code") or "").strip() or generate_coupon()
    if not str(context.get("coupon_code") or "").strip():
        await _emit_safe(emit, "Using synthetic user data")
    await _emit_safe(emit, f"[micro:{tid}] before — invalid coupon {code}")

    field_sel = await _first_matching_visible_selector(page, COUPON_FIELD_PATTERNS)
    if not field_sel:
        defects.append({"defect": "coupon_field_missing", "description": "No coupon field matched", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no field")
        return _result(tid, False, defects, "HIGH")

    if not await safe_fill(page, field_sel, code, timeout_ms=5000):
        defects.append({"defect": "coupon_fill_failed", "description": "safe_fill coupon failed", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — fill failed")
        return _result(tid, False, defects, "HIGH")

    apply_sel = await _first_matching_visible_selector(page, COUPON_APPLY_PATTERNS)
    if not apply_sel or not await safe_click(page, apply_sel, timeout_ms=6000):
        defects.append({"defect": "coupon_apply_failed", "description": "Could not apply coupon via safe_click", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — apply click failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1000)
    text = await _body_text_lower(page, 6000)
    err_signals = (
        "invalid",
        "not valid",
        "couldn't",
        "could not",
        "doesn't apply",
        "not apply",
        "error",
        "unable",
        "rejected",
        "not recognized",
        "wrong",
    )
    error_shown = any(s in text for s in err_signals) or await page.locator("[role='alert'], .error, [class*='error']").count() > 0

    if not error_shown:
        defects.append(
            {
                "defect": "coupon_no_error_shown",
                "description": f"Invalid code {code} did not surface an error message",
                "severity": "high",
                "page_url": page.url,
            }
        )

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0 and error_shown
    await _emit_safe(emit, f"[micro:{tid}] after — error_shown={error_shown}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_start_checkout(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "start_checkout"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — checkout")

    before = await _snapshot_page_signals(page)
    url_before = page.url or ""

    chk_sel = await _first_matching_visible_selector(page, CHECKOUT_CTA_PATTERNS)
    if not chk_sel:
        defects.append({"defect": "checkout_unavailable", "description": "No checkout control matched", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no CTA")
        return _result(tid, False, defects, "HIGH")

    if not await safe_click(page, chk_sel, timeout_ms=10_000):
        defects.append({"defect": "cannot_proceed_checkout", "description": "safe_click checkout failed", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — click failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1200)
    url_after = page.url or ""
    path_ok = any(x in url_after.lower() for x in ("checkout", "shipping", "payment", "delivery", "cart"))
    ui_delta = abs(int((await _snapshot_page_signals(page)).get("textLen", 0)) - int(before.get("textLen", 0))) > 80
    progressed = url_before != url_after or path_ok or ui_delta

    if not progressed:
        defects.append({"defect": "cannot_proceed_checkout", "description": "Checkout did not navigate or change page", "severity": "high", "page_url": page.url})

    ok = len(defects) == 0
    await _emit_safe(emit, f"[micro:{tid}] after — progressed={progressed}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_fill_address_form(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "fill_address_form"
    defects: list[dict[str, Any]] = []
    need_synthetic = not (
        str(context.get("shipping_address") or context.get("address") or "").strip()
        or str(context.get("shipping_phone") or context.get("phone") or "").strip()
    )
    if need_synthetic:
        prof = generate_user_profile()
        await _emit_safe(emit, "Using synthetic user data")
        parts = prof["name"].split(None, 1)
        context.setdefault("first_name", parts[0] if parts else "Test")
        context.setdefault("last_name", parts[1] if len(parts) > 1 else "User")
        context.setdefault("address", prof["address"])
        context.setdefault("phone", prof["phone"])
        context.setdefault("email", prof["email"])

    await _emit_safe(emit, f"[micro:{tid}] before — minimal address")

    fx = _checkout_shipping_fixture(context)
    full_name = f"{fx['first']} {fx['last']}".strip()
    phone = fx["phone"]
    addr = fx["address1"]

    name_sel = await _first_matching_visible_selector(page, ADDRESS_NAME_PATTERNS)
    addr_sel = await _first_matching_visible_selector(page, ADDRESS_LINE_PATTERNS)
    phone_sel = await _first_matching_visible_selector(page, PHONE_FIELD_PATTERNS)

    filled = 0
    if name_sel and await safe_fill(page, name_sel, full_name, timeout_ms=4000):
        filled += 1
        await _emit_safe(emit, f"[micro:{tid}] filled name")
    if addr_sel and await safe_fill(page, addr_sel, addr, timeout_ms=4000):
        filled += 1
        await _emit_safe(emit, f"[micro:{tid}] filled address")
    if phone_sel and await safe_fill(page, phone_sel, phone, timeout_ms=4000):
        filled += 1
        await _emit_safe(emit, f"[micro:{tid}] filled phone")

    if filled < 2:
        defects.append({"defect": "address_fields_missing", "description": "Could not fill at least name/address/phone (need 2+)", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — insufficient fields")
        return _result(tid, False, defects, "HIGH")

    cont_sel = await _first_matching_visible_selector(page, FORM_CONTINUE_PATTERNS)
    if cont_sel:
        await _emit_safe(emit, f"[micro:{tid}] submit/continue")
        await safe_click(page, cont_sel, timeout_ms=8000)
    await page.wait_for_timeout(900)

    if await _detect_validation_blockers(page):
        defects.append({"defect": "validation_blocked", "description": "Validation errors or alerts block progress", "severity": "high", "page_url": page.url})

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0
    await _emit_safe(emit, f"[micro:{tid}] after — ok={ok}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_place_order_attempt(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "place_order_attempt"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — place order click")

    terms_sel = await _first_matching_visible_selector(page, TERMS_CHECKBOX_PATTERNS)
    if terms_sel:
        await safe_click(page, terms_sel, timeout_ms=4000)
        await _emit_safe(emit, f"[micro:{tid}] accepted terms if present")

    place_sel = await _first_matching_visible_selector(page, PLACE_ORDER_PATTERNS)
    if not place_sel:
        defects.append({"defect": "place_order_broken", "description": "Place order control not found", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no button")
        return _result(tid, False, defects, "HIGH")

    url_b = page.url or ""
    text_b = await _body_text_lower(page, 4000)

    if not await safe_click(page, place_sel, timeout_ms=10_000):
        defects.append({"defect": "place_order_broken", "description": "Place order not clickable", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — click failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(2000)
    url_a = page.url or ""
    text_a = await _body_text_lower(page, 8000)

    success_hints = ("thank", "order confirm", "confirmation", "placed", "success", "received")
    pay_error_hints = ("declined", "payment failed", "card", "invalid cvc", "unable to process", "error processing")

    saw_success = any(h in text_a for h in success_hints)
    saw_pay_err = any(h in text_a for h in pay_error_hints)
    content_shift = text_a != text_b or url_a != url_b

    if not (saw_success or saw_pay_err or content_shift):
        defects.append({"defect": "place_order_no_effect", "description": "No success, payment error, or page change after place order", "severity": "high", "page_url": page.url})

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0
    await _emit_safe(emit, f"[micro:{tid}] after — success={saw_success} pay_err={saw_pay_err}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_contact_support(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "contact_support"
    defects: list[dict[str, Any]] = []
    has_email = str(context.get("contact_email") or context.get("email") or "").strip()
    has_msg = str(context.get("support_message") or "").strip()
    if not has_email or not has_msg:
        prof = generate_user_profile()
        await _emit_safe(emit, "Using synthetic user data")
        if not has_email:
            context.setdefault("contact_email", prof["email"])
            context.setdefault("email", prof["email"])
        if not has_msg:
            context["support_message"] = (
                f"Hello — this is a QA inquiry from {prof['name']}. Please confirm receipt."
            )

    await _emit_safe(emit, f"[micro:{tid}] before — contact form")

    msg = str(context.get("support_message") or "QA automated message — please ignore.").strip()
    email_val = str(context.get("contact_email") or context.get("email") or "qa-check@example.com").strip()

    email_sel = await _first_matching_visible_selector(page, CONTACT_EMAIL_PATTERNS)
    msg_sel = await _first_matching_visible_selector(page, CONTACT_MESSAGE_PATTERNS)

    if not email_sel or not msg_sel:
        defects.append({"defect": "contact_form_missing", "description": "Contact form fields not found", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no form")
        return _result(tid, False, defects, "HIGH")

    if not await safe_fill(page, email_sel, email_val, timeout_ms=5000):
        defects.append({"defect": "contact_form_not_working", "description": "Could not fill email", "severity": "high", "page_url": page.url})
    if not await safe_fill(page, msg_sel, msg, timeout_ms=5000):
        defects.append({"defect": "contact_form_not_working", "description": "Could not fill message", "severity": "high", "page_url": page.url})

    if any(d.get("defect") == "contact_form_not_working" for d in defects):
        await _emit_safe(emit, f"[micro:{tid}] after — fill failed")
        return _result(tid, False, defects, "HIGH")

    before = await _snapshot_page_signals(page)
    sub_sel = await _first_matching_visible_selector(page, CONTACT_SUBMIT_PATTERNS)
    if not sub_sel or not await safe_click(page, sub_sel, timeout_ms=8000):
        defects.append({"defect": "contact_form_not_working", "description": "Submit control missing or not clickable", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — submit failed")
        return _result(tid, False, defects, "HIGH")

    await page.wait_for_timeout(1200)
    text = await _body_text_lower(page, 6000)
    after = await _snapshot_page_signals(page)
    ok_signals = ("thank", "sent", "received", "success", "submitted")
    err_signals = ("error", "failed", "invalid", "try again")
    feedback = any(s in text for s in ok_signals + err_signals) or abs(
        int(after.get("textLen", 0)) - int(before.get("textLen", 0))
    ) > 40

    if not feedback:
        defects.append({"defect": "contact_form_not_working", "description": "No confirmation or error after submit", "severity": "high", "page_url": page.url})

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0
    await _emit_safe(emit, f"[micro:{tid}] after — feedback={feedback}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_check_page_load(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "check_page_load"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — load timing")

    await safe_click(page, "html", timeout_ms=2000)

    ms: float | None = None
    try:
        ms = await page.evaluate("""() => {
          const p = performance.timing;
          if (!p || !p.navigationStart || !p.loadEventEnd) return null;
          return Math.max(0, p.loadEventEnd - p.navigationStart);
        }""")
    except Exception as e:
        defects.append({"defect": "load_metric_error", "description": str(e)[:200], "severity": "medium", "page_url": page.url})

    threshold_ms = float(context.get("load_time_threshold_ms") or 5000)
    if ms is not None and ms > threshold_ms:
        defects.append(
            {
                "defect": "slow_page_load",
                "description": f"Load {int(ms)}ms exceeds {int(threshold_ms)}ms",
                "severity": "high",
                "page_url": page.url,
            }
        )

    ok = len([d for d in defects if d.get("severity") == "high"]) == 0 and (ms is None or ms <= threshold_ms)
    await _emit_safe(emit, f"[micro:{tid}] after — load_ms={ms}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))


async def task_check_navigation_links(page: Page, context: dict[str, Any], emit: EmitFn) -> MicroTaskResult:
    context = ensure_shared_context(context)
    tid = "check_navigation_links"
    defects: list[dict[str, Any]] = []
    await _emit_safe(emit, f"[micro:{tid}] before — main nav")

    url0 = page.url or ""
    nav_sel = await _first_matching_visible_selector(page, NAV_LINK_PATTERNS)
    if not nav_sel:
        defects.append({"defect": "broken_navigation", "description": "No main navigation links matched", "severity": "high", "page_url": page.url})
        await _emit_safe(emit, f"[micro:{tid}] after — no nav")
        return _result(tid, False, defects, "HIGH")

    try:
        n_links = await page.locator(nav_sel).count()
    except Exception as e:
        defects.append({"defect": "broken_navigation", "description": str(e)[:200], "severity": "high", "page_url": page.url})
        return _result(tid, False, defects, "HIGH")

    want = int(context.get("nav_max_clicks") or 3)
    want = max(2, min(3, want))
    n_iter = min(n_links, want)

    broken = 0
    for i in range(n_iter):
        await _emit_safe(emit, f"[micro:{tid}] nav {i + 1}/{n_iter}")
        before = await _snapshot_page_signals(page)
        url_before = page.url or ""
        if not await safe_click(page, nav_sel, timeout_ms=8000, nth=i):
            broken += 1
            defects.append({"defect": "broken_navigation", "description": f"Nav link {i} not clickable", "severity": "high", "page_url": page.url})
            continue
        await page.wait_for_timeout(700)
        after = await _snapshot_page_signals(page)
        changed = (page.url or "") != url_before or abs(int(after.get("textLen", 0)) - int(before.get("textLen", 0))) > 40
        if not changed:
            broken += 1
            defects.append({"defect": "broken_navigation", "description": f"Nav {i} produced no navigation", "severity": "medium", "page_url": page.url})
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=9000)
        except Exception:
            try:
                await page.goto(url0, wait_until="domcontentloaded", timeout=10_000)
            except Exception as e2:
                defects.append({"defect": "broken_navigation", "description": f"Restore failed: {e2!s}"[:200], "severity": "high", "page_url": page.url})
                broken += 1

    ok = broken == 0 and len([d for d in defects if d.get("severity") == "high"]) == 0
    await _emit_safe(emit, f"[micro:{tid}] after — broken={broken}")
    return _result(tid, ok, defects, _pick_impact(ok, defects))
