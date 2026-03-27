"""Build API-friendly structured output from crawl + executor results."""

from __future__ import annotations

from typing import Any

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


def _risk_weight(severity: str) -> int:
    match _normalize_severity(severity):
        case "critical":
            return 100
        case "high":
            return 70
        case "medium":
            return 40
        case "low":
            return 10
        case _:
            return 40


def _risk_level(score: int) -> str:
    if score > 200:
        return "HIGH RISK"
    if score > 100:
        return "MEDIUM RISK"
    return "LOW RISK"


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

        # Summary test failure if no finer-grained defect (avoid duplicate spam)
        if tr.result in ("fail", "error") and not any(
            i.get("test_id") == tr.test_id and i.get("defect") == "page_load_failure"
            for i in issues
        ):
            step_failures = [s for s in tr.step_results + tr.precondition_results if s.status == "fail"]
            if not step_failures and not any(
                not ar.passed for ar in tr.assertion_results
            ):
                issues.append(
                    {
                        "type": "test_result",
                        "defect": "test_failure",
                        "severity": "medium",
                        "message": tr.failure_reason or f"Test {tr.test_id} {tr.result}",
                        "test_id": tr.test_id,
                    },
                )

    return issues, console_errors_flat, failed_actions, missing_elements


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


def build_structured_output(
    *,
    site_model: SiteModel | None,
    run_result: RunResult | None,
    pipeline_error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Demo-friendly payload: summary counts, issues by severity, flat issues, crawl/actions."""
    issues, console_errors, failed_actions, missing_elements = _build_rule_based_issues(
        run_result, pipeline_error
    )
    issues_normalized = [{**i, "severity": _normalize_severity(i.get("severity"))} for i in issues]
    actions_run = _flatten_actions_run(run_result)

    risk_score = sum(_risk_weight(i.get("severity", "medium")) for i in issues_normalized)
    risk_level = _risk_level(risk_score)

    summary = {
        "total_pages_scanned": len(site_model.pages) if site_model else 0,
        "total_actions_run": len(actions_run),
        "total_issues_found": len(issues_normalized),
    }

    base: dict[str, Any] = {
        "summary": summary,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "partial": any(i.get("defect") == "auth_login_failed" for i in issues_normalized),
        "issues_by_severity": _issues_by_severity(issues_normalized),
        "issues": issues_normalized,
        "pages": _page_summaries(site_model),
        "actions_run": actions_run,
        "console_errors": console_errors,
        "failed_actions": failed_actions,
        "missing_elements": missing_elements,
    }
    if extra:
        base.update(extra)
    return base
