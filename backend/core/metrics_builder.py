"""Task-aware metrics derived from crawl pages, defects, and action trail."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# --- Normalization -----------------------------------------------------------


def _as_mapping(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}


def _normalize_pages(pages: Sequence[Any] | None) -> list[dict[str, Any]]:
    if not pages:
        return []
    return [_as_mapping(p) for p in pages]


def _normalize_defects(defects: Sequence[Any] | None) -> list[dict[str, Any]]:
    if not defects:
        return []
    out: list[dict[str, Any]] = []
    for d in defects:
        if isinstance(d, Mapping):
            out.append(dict(d))
        else:
            out.append(_as_mapping(d))
    return out


def _normalize_trail(action_trail: Sequence[Any] | None) -> list[dict[str, Any]]:
    if not action_trail:
        return []
    return [_as_mapping(a) for a in action_trail]


def _norm_task(scan_task: str | None) -> str:
    st = (scan_task or "full_app").strip().lower()
    if st in ("full_app", "auth", "checkout", "forms"):
        return st
    return "full_app"


def _page_url(page: Mapping[str, Any]) -> str:
    return str(page.get("url") or "").strip()


def _forms_count(page: Mapping[str, Any]) -> int:
    forms = page.get("forms")
    if isinstance(forms, list):
        return len(forms)
    return 0


# --- Heuristics --------------------------------------------------------------


def _login_related_action(action: Mapping[str, Any]) -> bool:
    phase = str(action.get("phase") or "").lower()
    if phase == "login":
        return True
    desc = str(action.get("description") or "").lower()
    needles = (
        "login",
        "sign in",
        "sign-in",
        "signin",
        "password",
        "credential",
        "authenticate",
        "session",
    )
    return any(n in desc for n in needles)


def _outcome(action: Mapping[str, Any]) -> str:
    return str(action.get("outcome") or "").lower().strip()


def _auth_success_rate(trail: list[dict[str, Any]]) -> float | None:
    relevant = [a for a in trail if _login_related_action(a)]
    terminal = [a for a in relevant if _outcome(a) in ("success", "failed", "warning", "skipped")]
    if not terminal:
        return None
    ok = sum(1 for a in terminal if _outcome(a) == "success")
    return round(100.0 * ok / len(terminal), 2)


def _url_lower(u: str) -> str:
    return (u or "").lower()


def _cart_pages_tested(pages: list[dict[str, Any]], trail: list[dict[str, Any]]) -> int:
    urls: set[str] = set()
    for p in pages:
        u = _url_lower(_page_url(p))
        if not u:
            continue
        if "cart" in u and "checkout" not in u:
            urls.add(u)
    for a in trail:
        u = _url_lower(str(a.get("target_url") or ""))
        if u and "cart" in u and "checkout" not in u:
            urls.add(u)
    return len(urls)


def _checkout_reached(pages: list[dict[str, Any]], trail: list[dict[str, Any]]) -> bool:
    for p in pages:
        if "checkout" in _url_lower(_page_url(p)):
            return True
    for a in trail:
        if "checkout" in _url_lower(str(a.get("target_url") or "")):
            return True
    return False


def _forms_tested_count(pages: list[dict[str, Any]]) -> int:
    total = 0
    for p in pages:
        total += _forms_count(p)
    return total


def _is_form_related_defect(d: Mapping[str, Any]) -> bool:
    t = str(d.get("type") or d.get("defect") or "").lower()
    msg = str(d.get("message") or "").lower()
    if "form" in t or "form" in msg:
        return True
    if any(x in msg for x in ("input", "field", "selector", "submit")):
        return True
    return False


def _is_validation_defect(d: Mapping[str, Any]) -> bool:
    msg = str(d.get("message") or "").lower()
    t = str(d.get("type") or d.get("defect") or "").lower()
    needles = (
        "validation",
        "invalid",
        "required",
        "pattern",
        "constraint",
    )
    return any(n in msg for n in needles) or any(n in t for n in needles)


def _validation_rate(defects: list[dict[str, Any]]) -> float | None:
    formish = [d for d in defects if _is_form_related_defect(d)]
    if not formish:
        return None
    val = sum(1 for d in formish if _is_validation_defect(d))
    return round(100.0 * val / len(formish), 2)


def _broken_element_count(defects: list[dict[str, Any]]) -> int:
    n = 0
    for d in defects:
        t = str(d.get("type") or "").lower()
        f = str(d.get("defect") or "").lower()
        if "broken_element" in t or "broken_element" in f or "broken" in f:
            n += 1
    return n


def _console_error_count(defects: list[dict[str, Any]]) -> int:
    n = 0
    for d in defects:
        t = str(d.get("type") or "").lower()
        f = str(d.get("defect") or "").lower()
        msg = str(d.get("message") or "").lower()
        if "console" in t or "console" in f:
            n += 1
        elif "console" in msg and ("error" in msg or "warning" in msg):
            n += 1
    return n


def _avg_navigate_load_ms(trail: list[dict[str, Any]]) -> float | None:
    durations: list[float] = []
    for a in trail:
        at = str(a.get("action_type") or "").lower()
        if at != "navigate":
            continue
        try:
            ms = float(a.get("duration_ms") or 0)
        except (TypeError, ValueError):
            continue
        if ms > 0:
            durations.append(ms)
    if not durations:
        return None
    return round(sum(durations) / len(durations), 2)


def _base_metrics(
    pages: list[dict[str, Any]],
    defects: list[dict[str, Any]],
    trail: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "pages_scanned": len(pages),
        "actions_taken": len(trail),
        "total_issues": len(defects),
    }


def build_metrics(
    scan_task: str | None,
    pages: Sequence[Any] | None,
    defects: Sequence[Any] | None,
    action_trail: Sequence[Any] | None,
) -> dict[str, Any]:
    """
    Build a structured metrics dict for dashboards and API payloads.

    *Base* metrics are always computed. Keys ``auth``, ``checkout``, ``forms``, and
    ``full_app`` are always present; exactly one is populated for the matching
    ``scan_task`` (``full_app`` | ``auth`` | ``checkout`` | ``forms``).

    Heuristics use URL keywords, defect ``type`` / ``defect`` / ``message``, and
    action trail ``phase`` / ``description`` / ``action_type`` / ``outcome``.
    """
    st = _norm_task(scan_task)
    plist = _normalize_pages(pages)
    dlist = _normalize_defects(defects)
    tlist = _normalize_trail(action_trail)

    base = _base_metrics(plist, dlist, tlist)
    login_actions = [a for a in tlist if _login_related_action(a)]
    out: dict[str, Any] = {
        "scan_task": st,
        "base": base,
        # Populated for matching task only; others stay None for a stable JSON shape.
        "auth": None,
        "checkout": None,
        "forms": None,
        "full_app": None,
    }

    if st == "auth":
        out["auth"] = {
            "login_attempts": len(login_actions),
            "success_rate": _auth_success_rate(tlist),
        }
    elif st == "checkout":
        out["checkout"] = {
            "cart_tested": _cart_pages_tested(plist, tlist),
            "checkout_reached": _checkout_reached(plist, tlist),
        }
    elif st == "forms":
        out["forms"] = {
            "forms_tested": _forms_tested_count(plist),
            "validation_rate": _validation_rate(dlist),
        }
    else:
        out["full_app"] = {
            "broken_elements": _broken_element_count(dlist),
            "console_errors": _console_error_count(dlist),
            "avg_load_time_ms": _avg_navigate_load_ms(tlist),
        }

    return out
