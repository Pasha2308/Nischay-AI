"""Build API-friendly structured output from crawl + executor results."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.defect_intelligence import (
    DefectIntelligenceService,
    _tag_business_impact,
    issue_dict_to_defect_mapping,
)

logger = logging.getLogger(__name__)

from shared.models.site_model import SiteModel
from shared.models.test_result import RunResult, StepResult, TestResult

# --- Rule-based defect detection (no ML) ---

_LOAD_FAIL_HINTS = (
    "net::err",
    "navigation",
    "goto",
    "page.goto",
    "ns_error",
    "err_connection",
    "err_name_not_resolved",
    "404",
    "403",
    "500",
    "502",
    "503",
)


def _is_page_load_context(message: str) -> bool:
    m = (message or "").lower()
    return any(h in m for h in _LOAD_FAIL_HINTS)


def _is_missing_element_error(message: str) -> bool:
    """Heuristic: Playwright / DOM errors that imply selector/target missing."""
    m = (message or "").lower()
    needles = (
        "timeout",
        "waiting for selector",
        "waiting for",
        "strict mode violation",
        "no node found",
        "element is not attached",
        "not visible",
        "not a locator",
        "does not match any node",
        "failed to find",
        "selector",
        "element not found",
    )
    return any(n in m for n in needles)


def _console_error_lines(console_logs: list[str]) -> list[str]:
    """Lines that look like console errors (exclude noisy favicon, etc.)."""
    out: list[str] = []
    for line in console_logs or []:
        low = line.lower()
        if "error" not in low and "warning" not in low:
            continue
        if "favicon" in low:
            continue
        out.append(line)
    return out


def _issue_is_meaningful(issue: dict[str, Any]) -> bool:
    """Drop generic / unactionable issues (e.g. \"test failure\", \"unknown error\")."""
    defect = str(issue.get("defect") or "").strip().lower()
    msg = str(issue.get("message") or "").strip().lower()
    if defect == "test_failure":
        return False
    if msg in ("unknown error", "test failure", ""):
        return False
    if "unknown error" in msg and len(msg) < 40:
        return False
    if not msg:
        return defect in ("auth_login_failed", "pipeline_failure", "console_error", "network_failure")
    return True


def _issue_display_title(issue: dict[str, Any]) -> str:
    t = str(issue.get("title") or "").strip()
    if t:
        return t
    d = str(issue.get("defect") or issue.get("type") or "issue").replace("_", " ").strip() or "issue"
    m = str(issue.get("message") or "").strip()
    if not m:
        return d[:1].upper() + d[1:]
    short = m if len(m) <= 140 else f"{m[:137]}…"
    return f"{d[:1].upper() + d[1:]} — {short}"


def _fix_suggestion_heuristic(issue: dict[str, Any]) -> str:
    defect = str(issue.get("defect") or issue.get("type") or "").lower()
    if "search" in defect:
        return "Validate search field selectors, catalog data, and that results render for representative queries."
    if "cart" in defect or "add_to_cart" in defect:
        return "Trace cart state (cookies/session), button handlers, and inventory APIs; retest add-to-cart on staging."
    if "checkout" in defect or "place_order" in defect or "payment" in defect:
        return "Review checkout funnel, payment gateway responses, and error handling; test with sandbox cards."
    if "login" in defect or "auth" in defect:
        return "Verify credentials flow, session cookies, and bot protection rules; align with identity provider."
    if "contact" in defect:
        return "Ensure contact form handlers, SMTP/API integrations, and validation messages are wired correctly."
    if "console" in defect:
        return "Open DevTools, fix the reported script error, and guard third-party scripts behind feature flags."
    return "Reproduce on staging, capture console/network logs, and patch the failing interaction or assertion."


def _finalize_issues_for_display(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in issues:
        if not _issue_is_meaningful(i):
            continue
        row = dict(i)
        row["title"] = _issue_display_title(row)
        if not str(row.get("fix_suggestion") or "").strip():
            row["fix_suggestion"] = _fix_suggestion_heuristic(row)
        bi = str(row.get("business_impact") or "").strip()
        if not bi or bi.lower() == "general":
            row["business_impact"] = _tag_business_impact(
                str(row.get("page_url") or ""),
                str(row.get("defect") or row.get("type") or ""),
                str(row.get("message") or ""),
            )
        out.append(row)
    return out


def _normalize_severity(raw: str | None) -> str:
    """Map issue severity to one of critical | high | medium | low."""
    s = (raw or "medium").strip().lower()
    if s in ("critical", "crit", "sev1", "blocker"):
        return "critical"
    if s in ("high", "error", "errors"):
        return "high"
    if s in ("medium", "med", "warn", "warning", "moderate"):
        return "medium"
    if s in ("low", "info", "note", "minor"):
        return "low"
    return "medium"


def _issues_by_severity(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }
    for issue in issues:
        normed = _normalize_severity(issue.get("severity"))
        row = {**issue, "severity": normed}
        buckets[normed].append(row)
    return buckets


# Severity point weights (summed, then capped at 100)
_SEVERITY_POINTS: dict[str, int] = {
    "critical": 40,
    "high": 25,
    "medium": 15,
    "low": 5,
}

_AUTH_CHECKOUT_MULTIPLIER = 1.5
_HOMEPAGE_MULTIPLIER = 1.2
_DEFECT_COUNT_PENALTY = 10
_DEFECT_COUNT_PENALTY_THRESHOLD = 10


def _is_homepage_url(page_url: str | None) -> bool:
    """Path is empty or '/' only (site root)."""
    u = (page_url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u)
        segs = [s for s in (p.path or "").split("/") if s]
        return len(segs) == 0
    except Exception:
        return False


def _is_auth_or_checkout_url(page_url: str | None) -> bool:
    u = (page_url or "").lower()
    if not u:
        return False
    keys = (
        "login", "signin", "sign-in", "signup", "sign-up", "register",
        "auth", "checkout", "cart", "payment", "billing", "order", "account",
    )
    return any(k in u for k in keys)


def _page_risk_multiplier(page_url: str | None) -> float:
    """Auth/checkout → ×1.5; homepage → ×1.2; take max applicable."""
    m = 1.0
    if _is_auth_or_checkout_url(page_url):
        m = max(m, _AUTH_CHECKOUT_MULTIPLIER)
    if _is_homepage_url(page_url):
        m = max(m, _HOMEPAGE_MULTIPLIER)
    return m


def _test_id_to_url(
    run_result: RunResult | None,
    site_model: SiteModel | None,
) -> dict[str, str]:
    """Map test_id → best-effort page URL for journey classification."""
    out: dict[str, str] = {}
    if not run_result:
        return out
    page_by_id: dict[str, str] = {}
    if site_model:
        for p in site_model.pages:
            if p.page_id and p.url:
                page_by_id[p.page_id] = p.url
    for tr in run_result.test_results:
        url = (tr.actual_url or "").strip()
        if not url and tr.target_page_id:
            url = (page_by_id.get(tr.target_page_id) or "").strip()
        if url:
            out[tr.test_id] = url
    return out


def _issue_page_url(
    issue: dict[str, Any],
    test_id_to_url: dict[str, str],
    fallback_url: str,
) -> str:
    tid = issue.get("test_id")
    if tid and isinstance(tid, str) and tid in test_id_to_url:
        return test_id_to_url[tid]
    pu = issue.get("page_url")
    if pu:
        return str(pu).strip()
    return fallback_url


def _risk_band_from_score(score: int) -> str:
    """CRITICAL / HIGH / MEDIUM / LOW."""
    s = max(0, min(100, int(score)))
    if s >= 75:
        return "CRITICAL"
    if s >= 50:
        return "HIGH"
    if s >= 25:
        return "MEDIUM"
    return "LOW"


def _risk_display_and_legacy(band: str) -> tuple[str, str]:
    """Display title + legacy string for API consumers."""
    return {
        "CRITICAL": ("Critical", "CRITICAL RISK"),
        "HIGH": ("High", "HIGH RISK"),
        "MEDIUM": ("Medium", "MEDIUM RISK"),
        "LOW": ("Low", "LOW RISK"),
    }.get(band, ("Low", "LOW RISK"))


def _compute_aggregate_risk_score(
    issues: list[dict[str, Any]],
    run_result: RunResult | None,
    site_model: SiteModel | None,
) -> tuple[int, str, str, dict[str, Any]]:
    """
    Sum per issue: severity_points × page_multiplier; cap at 100.
    If defect count > 10, add +10 penalty (then cap).
    Returns (score, risk_level display, risk_level_legacy, risk dict with score + level).
    """
    empty_risk = {"score": 0, "level": "LOW"}
    if not issues:
        return 0, "Low", "LOW RISK", empty_risk

    test_id_to_url = _test_id_to_url(run_result, site_model)
    fallback_url = ""
    try:
        if run_result and getattr(run_result, "target_url", None):
            fallback_url = str(run_result.target_url).strip()
    except Exception:
        fallback_url = ""

    total = 0.0
    for issue in issues:
        try:
            sev = _normalize_severity(issue.get("severity"))
            pts = float(_SEVERITY_POINTS.get(sev, 15))
            url = _issue_page_url(issue, test_id_to_url, fallback_url)
            m = _page_risk_multiplier(url)
            total += pts * m
        except Exception:
            continue

    n_defects = len(issues)
    if n_defects > _DEFECT_COUNT_PENALTY_THRESHOLD:
        total += float(_DEFECT_COUNT_PENALTY)

    score = int(min(100, round(total)))
    band = _risk_band_from_score(score)
    display, legacy = _risk_display_and_legacy(band)
    risk_detail: dict[str, Any] = {"score": score, "level": band}
    return score, display, legacy, risk_detail


def _build_rule_based_issues(
    run_result: RunResult | None,
    pipeline_error: str | None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (issues, console_errors, failed_actions, missing_elements)."""
    issues: list[dict[str, Any]] = []
    console_errors_flat: list[str] = []
    failed_actions: list[dict[str, Any]] = []
    missing_elements: list[dict[str, Any]] = []

    if pipeline_error:
        sev = "critical" if _is_page_load_context(pipeline_error) else "high"
        issues.append(
            {
                "type": "pipeline_error",
                "defect": "pipeline_failure",
                "severity": _normalize_severity(sev),
                "message": pipeline_error,
            },
        )
        return issues, console_errors_flat, failed_actions, missing_elements

    if not run_result:
        return issues, console_errors_flat, failed_actions, missing_elements

    for tr in run_result.test_results:
        if (tr.failure_reason or "").startswith("AUTH_LOGIN_FAILED:"):
            issues.append(
                {
                    "type": "auth_error",
                    "defect": "auth_login_failed",
                    "severity": "high",
                    "message": tr.failure_reason.replace("AUTH_LOGIN_FAILED:", "").strip()
                    or "Login failed",
                    "test_id": tr.test_id,
                }
            )
            continue

        # Console errors from evidence → HIGH
        for raw in _console_error_lines(tr.evidence.console_logs):
            console_errors_flat.append(raw)
            issues.append(
                {
                    "type": "console_error",
                    "defect": "console_error",
                    "severity": "high",
                    "message": raw[:2000],
                    "test_id": tr.test_id,
                },
            )

        for sr in tr.precondition_results:
            _emit_step_defects(tr, sr, "precondition", issues, failed_actions, missing_elements)
        for sr in tr.step_results:
            _emit_step_defects(tr, sr, "step", issues, failed_actions, missing_elements)

        for ar in tr.assertion_results:
            if ar.passed:
                continue
            if ar.assertion_type == "page_loaded":
                issues.append(
                    {
                        "type": "assertion_failure",
                        "defect": "page_load_failure",
                        "severity": "critical",
                        "message": ar.message or "Page did not load as expected",
                        "test_id": tr.test_id,
                        "assertion_type": ar.assertion_type,
                    },
                )
            else:
                issues.append(
                    {
                        "type": "assertion_failure",
                        "defect": "assertion_failure",
                        "severity": "medium",
                        "message": ar.message or f"Assertion {ar.assertion_type} failed",
                        "test_id": tr.test_id,
                        "assertion_type": ar.assertion_type,
                    },
                )

    return issues, console_errors_flat, failed_actions, missing_elements


def _severity_from_qa_defect_dict(d: dict[str, Any]) -> str:
    """Map active-QA defect payload to severity for risk scoring."""
    raw = d.get("severity")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    t = f"{d.get('defect', '')} {d.get('type', '')}".lower()
    if "slow" in t or "performance" in t:
        return "medium"
    if "console" in t:
        return "high"
    if "broken" in t or "navigation" in t or "form" in t:
        return "medium"
    return "medium"


def _issues_from_qa_defects(run_result: RunResult | None) -> list[dict[str, Any]]:
    """Turn per-page active QA defect dicts into risk issues."""
    out: list[dict[str, Any]] = []
    if not run_result:
        return out
    for tr in run_result.test_results:
        for block in tr.qa_defects_by_page or []:
            page_url = str(block.get("page_url") or "")
            for d in block.get("defects") or []:
                if not isinstance(d, dict):
                    continue
                dtype = str(d.get("defect") or d.get("type") or "qa_defect")
                msg = str(d.get("description") or "")[:2000].strip()
                if not msg or msg.lower() in ("unknown error", "test failure"):
                    continue
                out.append(
                    {
                        "type": dtype,
                        "defect": dtype,
                        "severity": _normalize_severity(_severity_from_qa_defect_dict(d)),
                        "message": msg,
                        "test_id": tr.test_id,
                        "page_url": page_url,
                    }
                )
    return out


def _fallback_console_extra(line: str) -> bool:
    """Console signals not already covered by _console_error_lines (second pass)."""
    low = (line or "").lower()
    if not low.strip() or "favicon" in low:
        return False
    if line in _console_error_lines([line]):
        return False
    needles = (
        "net::err",
        "failed to fetch",
        "load failed",
        "content security policy",
        "mixed content",
        "blocked by",
        "cors policy",
        "chunkloaderror",
        "loading chunk",
        "refused to execute",
        "refused to apply",
    )
    return any(n in low for n in needles)


def _fallback_detection_issues(
    run_result: RunResult,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Second pass when primary issue list is empty: console, performance/network, broken assets.
    Returns (issues, extra console lines for structured payload).
    """
    issues: list[dict[str, Any]] = []
    extra_console: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    def _add_issue(
        defect: str,
        itype: str,
        severity: str,
        message: str,
        test_id: str,
    ) -> None:
        key = (test_id, defect, message[:160])
        if key in seen:
            return
        seen.add(key)
        issues.append(
            {
                "type": itype,
                "defect": defect,
                "severity": _normalize_severity(severity),
                "message": message[:2000],
                "test_id": test_id,
            }
        )

    for tr in run_result.test_results:
        tid = tr.test_id
        # --- Console (broader than first pass) ---
        for raw in tr.evidence.console_logs or []:
            if _fallback_console_extra(raw):
                _add_issue("console_error_fallback", "console_error", "high", raw, tid)
                extra_console.append(raw)

        # --- Performance / HTTP errors from network log ---
        for entry in tr.evidence.network_log or []:
            url = str(entry.get("url") or "")
            try:
                st = int(entry.get("status") or 0)
            except (TypeError, ValueError):
                st = 0
            if st < 400:
                continue
            low_u = url.lower()
            asset_exts = (
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".woff", ".woff2",
            )
            if st == 404 and any(low_u.endswith(ext) for ext in asset_exts):
                _add_issue(
                    "broken_asset_404",
                    "broken_element",
                    "medium",
                    f"404 for asset {url[:800]}",
                    tid,
                )
            else:
                _add_issue(
                    "http_error",
                    "network_failure",
                    "high" if st >= 500 else "medium",
                    f"HTTP {st} {url[:800]}",
                    tid,
                )

    return issues, extra_console


NO_DETECTION_GAP_ISSUE: dict[str, Any] = {
    "type": "no_detection_fallback",
    "defect": "no_detection_fallback",
    "severity": "low",
    "business_impact": "trust",
    "message": "No issues detected — possible detection gap",
}


def _apply_risk_detection_fallbacks(
    issues: list[dict[str, Any]],
    run_result: RunResult | None,
    pipeline_error: str | None,
    console_errors_flat: list[str],
) -> None:
    """
    If total defects == 0 after rule-based + QA defects: run fallback detection.
    If still 0 and we have a run: inject low-severity detection-gap issue.
    Mutates ``issues`` and ``console_errors_flat`` in place.
    Caller must extend ``issues`` with :func:`_issues_from_qa_defects` before this.
    """
    if pipeline_error or not run_result:
        return

    if len(issues) > 0:
        return

    fb_issues, fb_console = _fallback_detection_issues(run_result)
    issues.extend(fb_issues)
    console_errors_flat.extend(fb_console)

    if len(issues) > 0:
        return

    issues.append(dict(NO_DETECTION_GAP_ISSUE))


def _emit_step_defects(
    tr: TestResult,
    sr: StepResult,
    phase: str,
    issues: list[dict[str, Any]],
    failed_actions: list[dict[str, Any]],
    missing_elements: list[dict[str, Any]],
) -> None:
    if sr.status != "fail":
        return

    msg = sr.error_message or f"{sr.action_type} failed"
    action_rec = {
        "test_id": tr.test_id,
        "phase": phase,
        "step_index": sr.step_index,
        "action_type": sr.action_type,
        "selector": sr.selector,
        "value": sr.value,
        "error_message": msg,
    }
    failed_actions.append(action_rec)

    missing = _is_missing_element_error(msg)
    if missing:
        missing_elements.append(
            {
                "test_id": tr.test_id,
                "phase": phase,
                "step_index": sr.step_index,
                "action_type": sr.action_type,
                "selector": sr.selector,
                "message": msg[:2000],
            },
        )

    if sr.action_type == "navigate":
        issues.append(
            {
                "type": "failed_action",
                "defect": "page_load_failure",
                "severity": "critical",
                "message": msg,
                "test_id": tr.test_id,
                "phase": phase,
                "step_index": sr.step_index,
                "action_type": sr.action_type,
            },
        )
        return

    if sr.action_type == "click":
        issues.append(
            {
                "type": "failed_action",
                "defect": "missing_element" if missing else "failed_action",
                "severity": "medium",
                "message": msg,
                "test_id": tr.test_id,
                "phase": phase,
                "step_index": sr.step_index,
                "action_type": sr.action_type,
                "selector": sr.selector,
            },
        )
        return

    if sr.action_type == "fill":
        issues.append(
            {
                "type": "failed_action",
                "defect": "missing_element" if missing else "failed_action",
                "severity": "medium",
                "message": msg,
                "test_id": tr.test_id,
                "phase": phase,
                "step_index": sr.step_index,
                "action_type": sr.action_type,
                "selector": sr.selector,
            },
        )
        return

    issues.append(
        {
            "type": "failed_action",
            "defect": "missing_element" if missing else "failed_action",
            "severity": "medium",
            "message": msg,
            "test_id": tr.test_id,
            "phase": phase,
            "step_index": sr.step_index,
            "action_type": sr.action_type,
            "selector": sr.selector,
        },
    )


def _page_summaries(site_model: SiteModel | None) -> list[dict[str, Any]]:
    if not site_model:
        return []
    return [
        {
            "page_id": p.page_id,
            "url": p.url,
            "title": p.title or "",
            "page_type": p.page_type,
        }
        for p in site_model.pages
    ]


def site_pages_payload(site_model: SiteModel | None) -> dict[str, Any]:
    """Authoritative crawl page list and count for orchestrator payloads (matches ``len(pages)``)."""
    pages = _page_summaries(site_model)
    return {"pages": pages, "pages_scanned": len(pages)}


def _flatten_actions_run(run_result: RunResult | None) -> list[dict[str, Any]]:
    if not run_result:
        return []
    out: list[dict[str, Any]] = []
    for tr in run_result.test_results:
        out.extend(_steps_for_test(tr, tr.precondition_results, "precondition"))
        out.extend(_steps_for_test(tr, tr.step_results, "step"))
    return out


def _steps_for_test(
    tr: TestResult,
    steps: list[StepResult],
    kind: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sr in steps:
        rows.append(
            {
                "test_id": tr.test_id,
                "test_name": tr.test_name,
                "phase": kind,
                "step_index": sr.step_index,
                "action_type": sr.action_type,
                "selector": sr.selector,
                "value": sr.value,
                "description": sr.description,
                "status": sr.status,
                "error_message": sr.error_message,
                "screenshot_path": sr.screenshot_path,
            }
        )
    return rows


async def _enrich_issues_with_intelligence(
    issues: list[dict[str, Any]],
    run_result: RunResult | None,
    site_model: SiteModel | None,
) -> list[dict[str, Any]]:
    """Attach recurring, fix_suggestion, business_impact via DefectIntelligenceService."""
    if not issues:
        return []

    test_id_to_url = _test_id_to_url(run_result, site_model)
    fallback_url = ""
    try:
        if run_result and getattr(run_result, "target_url", None):
            fallback_url = str(run_result.target_url).strip()
    except Exception:
        fallback_url = ""

    service = DefectIntelligenceService()

    async def _enrich_one(issue: dict[str, Any], session: AsyncSession | None) -> dict[str, Any]:
        tid = issue.get("test_id")
        url = ""
        if tid and isinstance(tid, str) and tid in test_id_to_url:
            url = test_id_to_url[tid]
        elif fallback_url:
            url = fallback_url
        mapping = issue_dict_to_defect_mapping(issue, url)
        try:
            enriched = await service.enrich_defect(mapping, session)
            merged: dict[str, Any] = {**issue}
            merged["severity"] = _normalize_severity(enriched.get("severity"))
            merged["recurring"] = bool(enriched.get("recurring", False))
            merged["fix_suggestion"] = str(enriched.get("fix_suggestion") or "")
            bi0 = str(enriched.get("business_impact") or "").strip()
            if not bi0 or bi0.lower() == "general":
                merged["business_impact"] = _tag_business_impact(
                    url,
                    str(issue.get("type") or issue.get("defect") or ""),
                    str(issue.get("message") or ""),
                )
            else:
                merged["business_impact"] = bi0
            return merged
        except Exception as e:
            logger.debug("enrich_defect failed: %s", e)
            return {
                **issue,
                "recurring": False,
                "fix_suggestion": "",
                "business_impact": _tag_business_impact(
                    url,
                    str(issue.get("type") or issue.get("defect") or ""),
                    str(issue.get("message") or ""),
                ),
            }

    try:
        from backend.db.session import get_async_session_maker

        session_maker = get_async_session_maker()
    except Exception as e:
        logger.debug("Database session factory unavailable: %s", e)
        session_maker = None

    if session_maker is not None:
        try:
            async with session_maker() as session:
                return [await _enrich_one(issue, session) for issue in issues]
        except Exception as e:
            logger.warning("Defect intelligence DB session failed; using offline enrichment: %s", e)
            return [await _enrich_one(issue, None) for issue in issues]

    return [await _enrich_one(issue, None) for issue in issues]


async def build_structured_output(
    *,
    site_model: SiteModel | None,
    run_result: RunResult | None,
    pipeline_error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Demo-friendly payload: summary counts, issues by severity, flat issues, crawl/actions."""
    merged_extra = dict(extra or {})
    pages_override = merged_extra.pop("pages", None)
    pages_scanned_override = merged_extra.pop("pages_scanned", None)
    summary_extra = merged_extra.pop("summary", None)

    if pages_override is not None:
        pages_list: list[dict[str, Any]] = list(pages_override)
        pages_scanned = len(pages_list)
    elif site_model is not None:
        pages_list = _page_summaries(site_model)
        pages_scanned = len(pages_list)
    else:
        pages_list = []
        pages_scanned = 0

    if pages_scanned_override is not None and pages_override is None:
        try:
            pages_scanned = int(pages_scanned_override)
        except (TypeError, ValueError):
            pass

    issues, console_errors, failed_actions, missing_elements = _build_rule_based_issues(
        run_result, pipeline_error
    )
    if not pipeline_error and run_result:
        issues.extend(_issues_from_qa_defects(run_result))
        _apply_risk_detection_fallbacks(issues, run_result, pipeline_error, console_errors)

    issues_normalized = [{**i, "severity": _normalize_severity(i.get("severity"))} for i in issues]
    issues_enriched = await _enrich_issues_with_intelligence(
        issues_normalized, run_result, site_model
    )
    issues_out = _finalize_issues_for_display(issues_enriched)
    actions_run = _flatten_actions_run(run_result)

    risk_score, risk_level, risk_level_legacy, risk_detail, *_ = _compute_aggregate_risk_score(
        issues_out, run_result, site_model
    )
    auth_failed = any(i.get("defect") == "auth_login_failed" for i in issues_out)
    auth_succeeded = bool(
        run_result
        and any(tr.test_id == "auth_login" and tr.result == "pass" for tr in run_result.test_results)
    )

    base: dict[str, Any] = {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_level_legacy": risk_level_legacy,
        "risk": risk_detail,
        "partial": auth_failed,
        "auth_status": "failed" if auth_failed else ("success" if auth_succeeded else "not_attempted"),
        "issues_by_severity": _issues_by_severity(issues_out),
        "issues": issues_out,
        "pages": pages_list,
        "pages_scanned": pages_scanned,
        "actions_run": actions_run,
        "console_errors": console_errors,
        "failed_actions": failed_actions,
        "missing_elements": missing_elements,
    }
    base.update(merged_extra)
    base["risk_score"] = risk_score
    base["risk_level"] = risk_level
    base["risk_level_legacy"] = risk_level_legacy
    base["risk"] = risk_detail
    base["pages"] = pages_list
    base["pages_scanned"] = pages_scanned
    summary_out = {
        "total_pages_scanned": pages_scanned,
        "total_actions_run": len(actions_run),
        "total_issues_found": len(issues_out),
    }
    if isinstance(summary_extra, dict):
        summary_out = {**summary_extra, **summary_out}
    base["summary"] = summary_out
    return base
