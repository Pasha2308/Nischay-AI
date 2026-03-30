from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

BusinessImpact = Literal["revenue", "trust", "ux", "compliance", "performance"]
Severity = Literal["critical", "high", "medium", "low"]


def _short_path(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return "unknown page"
    try:
        p = urlparse(u)
        path = p.path or "/"
        return path if len(path) <= 80 else f"{path[:77]}…"
    except Exception:
        return u[:80]


def _default_business_impact(defect_code: str, page_url: str, description: str) -> BusinessImpact:
    d = (defect_code or "").lower()
    u = (page_url or "").lower()
    msg = (description or "").lower()
    combined = f"{d} {u} {msg}"
    if any(k in combined for k in ("checkout", "payment", "place_order", "order", "billing")):
        return "revenue"
    if any(k in combined for k in ("add_to_cart", "cart", "basket")):
        return "revenue"
    if any(k in combined for k in ("login", "signin", "sign-in", "auth", "password", "session")):
        return "revenue"
    if any(k in combined for k in ("search", "no_results", "product_click_failed", "pdp_not_loaded")):
        return "revenue"
    if any(k in combined for k in ("slow", "latency", "lcp", "load time", "page_load", "performance")):
        return "performance"
    if any(k in combined for k in ("alt text", "aria", "accessibility", "a11y", "captcha")):
        return "compliance"
    if any(k in combined for k in ("console_error", "js error", "uncaught", "typeerror", "syntaxerror")):
        return "trust"
    return "ux"


def _default_severity(defect_code: str, business_impact: BusinessImpact) -> Severity:
    d = (defect_code or "").lower()
    if any(k in d for k in ("checkout", "payment", "place_order", "login", "auth")):
        return "critical"
    if business_impact == "revenue":
        return "high"
    if business_impact == "performance":
        return "medium"
    if business_impact == "compliance":
        return "medium"
    if business_impact == "trust":
        return "medium"
    return "low"


def _default_user_view(defect_code: str, page_url: str) -> str:
    path = _short_path(page_url)
    d = (defect_code or "").lower()
    if "add_to_cart" in d:
        return f"User tries to add an item to cart on {path}, but nothing gets added."
    if "checkout" in d or "place_order" in d or "payment" in d:
        return f"User cannot complete checkout on {path}; purchase flow is blocked."
    if "login" in d or "auth" in d:
        return f"User cannot sign in on {path}; account access is blocked."
    if "search" in d or "no_results" in d:
        return f"User searches on {path} but cannot find products via search."
    if "navigation" in d:
        return f"User clicks navigation on {path} but it does not take them to the expected page."
    if "console_error" in d:
        return f"User may see broken or inconsistent UI behavior on {path} due to a client-side error."
    return f"User hits a broken or confusing experience on {path}."


def _default_how_to_fix(defect_code: str, element: str, page_url: str, description: str) -> str:
    path = _short_path(page_url)
    el = (element or "").strip()
    d = (defect_code or "").lower()
    if "add_to_cart" in d:
        return (
            f"Verify the add-to-cart handler for {el or 'the add-to-cart control'} on {path}: "
            "ensure click triggers the expected add-to-cart request and the cart count/state updates."
        )
    if "search" in d:
        return (
            f"Verify the search UI ({el or 'search input'}) on {path}: "
            "ensure input events submit, backend returns results, and the results list renders."
        )
    if "login" in d or "auth" in d:
        return (
            f"Verify login form submission ({el or 'login controls'}) on {path}: "
            "ensure credentials are accepted, session cookies/token are set, and redirect completes."
        )
    if "checkout" in d or "payment" in d or "place_order" in d:
        return (
            f"Verify checkout actions ({el or 'checkout control'}) on {path}: "
            "ensure the CTA is enabled, required fields validate, and navigation/API responses succeed."
        )
    if "console_error" in d:
        return f"Fix the client-side error on {path}. Start with: {description[:180]}."
    return f"Reproduce on {path}, identify the failing element ({el or 'unknown'}), and fix the underlying handler/state."


def make_defect(
    *,
    defect: str,
    description: str,
    page_url: str,
    element: str | None = None,
    title: str | None = None,
    user_view: str | None = None,
    how_to_fix: str | None = None,
    severity: str | None = None,
    business_impact: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical defect dict that always carries:
      title, description, element, user_view, how_to_fix, severity, business_impact, page_url
    """
    dcode = str(defect or "unknown")
    purl = str(page_url or "")
    desc = str(description or "")

    impact: BusinessImpact = _default_business_impact(dcode, purl, desc)
    if business_impact in ("revenue", "trust", "ux", "compliance", "performance"):
        impact = business_impact  # type: ignore[assignment]

    sev: Severity = _default_severity(dcode, impact)
    if severity in ("critical", "high", "medium", "low"):
        sev = severity  # type: ignore[assignment]

    el = (element or "").strip()
    t = (title or "").strip() or f"{dcode.replace('_', ' ').strip().capitalize()} on {_short_path(purl)}"
    generic_titles = {
        "issue detected that may affect user experience",
        "review and fix this issue",
        "issue detected",
    }
    if (not t) or (len(t.strip()) < 15) or (t.strip().lower() in generic_titles):
        t = "DEFECT_TITLE_MISSING — fix in backend/core/defects.py"
    uv = (user_view or "").strip() or _default_user_view(dcode, purl)
    fix = (how_to_fix or "").strip() or _default_how_to_fix(dcode, el, purl, desc)

    out: dict[str, Any] = {
        "defect": dcode,
        "title": t,
        "description": desc,
        "element": el or "unknown",
        "user_view": uv,
        "how_to_fix": fix,
        "severity": sev,
        "business_impact": impact,
        "page_url": purl,
    }
    if extra:
        out.update(extra)
    return out

