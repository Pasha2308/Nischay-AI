"""
UX Scoring Engine for Nischay AI.
Rates websites on USER EXPERIENCE quality, not technical genuinity.

Scoring philosophy:
  A real user visits an e-commerce site to FIND, EVALUATE, and BUY.
  Every issue is scored by how much it HURTS that journey.

UX Score = 100 (perfect) minus penalties for UX-hurting issues.
Risk Score = inverse of UX score (high UX = low risk).

Categories rated:
  1. Navigation & Findability   — can users find what they want?
  2. Page Clarity               — is content clear and readable?
  3. Interaction Feedback       — do actions give clear responses?
  4. Conversion Flow            — can users complete checkout?
  5. Error Recovery             — are errors helpful or confusing?
  6. Performance Feel           — does slowness frustrate users?
  7. Mobile Usability           — works on phones?
  8. Accessibility              — usable by everyone?
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# ── UX Impact definitions ──────────────────────────────────────────────────

UX_ISSUE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "page_load_failure": {
        "ux_category": "Conversion Flow",
        "ux_impact": "CRITICAL",
        "ux_penalty": 40,
        "user_message": "Page failed to load — users cannot proceed",
        "improvement": (
            "Fix the server error. Users who hit this leave "
            "immediately and never return."
        ),
        "affects": "All users on this page",
    },
    "checkout_broken": {
        "ux_category": "Conversion Flow",
        "ux_impact": "CRITICAL",
        "ux_penalty": 40,
        "user_message": "Checkout flow is broken",
        "improvement": (
            "Restore the checkout flow immediately. "
            "Every minute this is broken = lost revenue."
        ),
        "affects": "100% of purchasing users",
    },
    "payment_error": {
        "ux_category": "Conversion Flow",
        "ux_impact": "CRITICAL",
        "ux_penalty": 35,
        "user_message": "Payment step has errors",
        "improvement": (
            "Test all payment methods. Payment failures "
            "destroy user trust permanently."
        ),
        "affects": "All users attempting to purchase",
    },
    "add_to_cart_broken": {
        "ux_category": "Conversion Flow",
        "ux_impact": "HIGH",
        "ux_penalty": 30,
        "user_message": "Add to cart button is not working",
        "improvement": (
            "Fix the cart button. This is the primary "
            "action on product pages."
        ),
        "affects": "All users on product pages",
    },
    "console_error": {
        "ux_category": "Page Clarity",
        "ux_impact": "HIGH",
        "ux_penalty": 20,
        "user_message": (
            "JavaScript errors are running silently "
            "in the background"
        ),
        "improvement": (
            "Fix JS errors. Even if invisible to users, "
            "they cause unpredictable behavior — "
            "buttons that don't respond, forms that "
            "don't submit, prices that don't update."
        ),
        "affects": "Users on affected pages",
    },
    "broken_image": {
        "ux_category": "Page Clarity",
        "ux_impact": "HIGH",
        "ux_penalty": 18,
        "user_message": "Product images are missing",
        "improvement": (
            "Fix broken image URLs. Users need to see "
            "products before they buy. Missing images "
            "signal an untrustworthy or abandoned site."
        ),
        "affects": "Users viewing affected products",
    },
    "broken_link": {
        "ux_category": "Navigation & Findability",
        "ux_impact": "HIGH",
        "ux_penalty": 15,
        "user_message": "Links lead to dead pages (404 errors)",
        "improvement": (
            "Fix or redirect broken links. Dead ends "
            "frustrate users and signal poor maintenance."
        ),
        "affects": "Users following navigation links",
    },
    "missing_alt_text": {
        "ux_category": "Accessibility",
        "ux_impact": "MEDIUM",
        "ux_penalty": 8,
        "user_message": (
            "Images have no text description "
            "(accessibility issue)"
        ),
        "improvement": (
            "Add descriptive alt text to all images. "
            "This helps visually impaired users and "
            "improves SEO ranking."
        ),
        "affects": "Screen reader users, SEO",
    },
    "slow_page_load": {
        "ux_category": "Performance Feel",
        "ux_impact": "MEDIUM",
        "ux_penalty": 15,
        "user_message": "Pages take too long to load",
        "improvement": (
            "Optimize images, enable caching, reduce "
            "JS bundle size. 53% of users abandon "
            "pages that take over 3 seconds."
        ),
        "affects": "All users, especially mobile",
    },
    "very_slow_page_load": {
        "ux_category": "Performance Feel",
        "ux_impact": "HIGH",
        "ux_penalty": 25,
        "user_message": "Pages are critically slow (6+ seconds)",
        "improvement": (
            "Critical performance issue. Implement "
            "CDN, lazy loading, and server-side "
            "optimization immediately."
        ),
        "affects": "All users — severe bounce rate impact",
    },
    "form_no_validation": {
        "ux_category": "Interaction Feedback",
        "ux_impact": "MEDIUM",
        "ux_penalty": 12,
        "user_message": (
            "Forms accept invalid or empty input "
            "without warning"
        ),
        "improvement": (
            "Add clear validation messages. Users "
            "need to know what went wrong and how "
            "to fix it — not just a generic error."
        ),
        "affects": "Users filling forms (checkout, signup, search)",
    },
    "missing_form_label": {
        "ux_category": "Page Clarity",
        "ux_impact": "MEDIUM",
        "ux_penalty": 8,
        "user_message": "Form fields have no labels",
        "improvement": (
            "Add visible labels to all form fields. "
            "Users should never have to guess what "
            "a field is asking for."
        ),
        "affects": "All users on forms, screen reader users",
    },
    "no_error_message": {
        "ux_category": "Error Recovery",
        "ux_impact": "MEDIUM",
        "ux_penalty": 10,
        "user_message": "Errors occur without helpful messages",
        "improvement": (
            "Show specific, actionable error messages. "
            "'Something went wrong' is not helpful. "
            "Tell users exactly what failed and "
            "what to do next."
        ),
        "affects": "Users encountering errors",
    },
    "mixed_content": {
        "ux_category": "Page Clarity",
        "ux_impact": "MEDIUM",
        "ux_penalty": 10,
        "user_message": (
            "Site loads insecure resources on a "
            "secure page"
        ),
        "improvement": (
            "Update all resource URLs to HTTPS. "
            "Browsers warn users about mixed content — "
            "this destroys purchase confidence."
        ),
        "affects": "All users, especially on checkout",
    },
    "low_color_contrast": {
        "ux_category": "Page Clarity",
        "ux_impact": "LOW",
        "ux_penalty": 5,
        "user_message": "Text is hard to read (low contrast)",
        "improvement": (
            "Increase text-to-background contrast ratio "
            "to at least 4.5:1. Poor contrast causes "
            "eye strain and loses users with "
            "visual impairments."
        ),
        "affects": "Users with visual impairments, elderly users",
    },
    "no_mobile_viewport": {
        "ux_category": "Mobile Usability",
        "ux_impact": "HIGH",
        "ux_penalty": 20,
        "user_message": "Site is not optimized for mobile",
        "improvement": (
            "Add responsive design and mobile viewport "
            "meta tag. Over 60% of e-commerce traffic "
            "is mobile."
        ),
        "affects": "60%+ of all users",
    },
    "search_not_working": {
        "ux_category": "Navigation & Findability",
        "ux_impact": "HIGH",
        "ux_penalty": 22,
        "user_message": "Search functionality is broken",
        "improvement": (
            "Fix the search feature. Users who search "
            "have high purchase intent — broken search "
            "directly loses sales."
        ),
        "affects": "High-intent buyers using search",
    },
}

DEFAULT_UX_DEFINITION: dict[str, Any] = {
    "ux_category": "General",
    "ux_impact": "MEDIUM",
    "ux_penalty": 10,
    "user_message": "DEFECT_TITLE_MISSING — fix in backend/ux_scorer.py",
    "improvement": (
        "DEFECT_TITLE_MISSING — fix in backend/ux_scorer.py"
    ),
    "affects": "Some users",
}

UX_SCORE_LABELS: list[tuple[int, str, str]] = [
    (90, "EXCELLENT UX", "#00C896"),
    (75, "GOOD UX", "#00D4FF"),
    (55, "NEEDS WORK", "#F5A623"),
    (35, "POOR UX", "#FF6B35"),
    (0, "CRITICAL UX ISSUES", "#FF4444"),
]

CATEGORY_WEIGHTS: dict[str, float] = {
    "Conversion Flow": 1.5,
    "Navigation & Findability": 1.3,
    "Performance Feel": 1.2,
    "Page Clarity": 1.1,
    "Interaction Feedback": 1.0,
    "Error Recovery": 1.0,
    "Mobile Usability": 1.2,
    "Accessibility": 0.8,
    "General": 1.0,
}


@dataclass
class UXIssue:
    """A single UX issue with full context for the user."""

    original_type: str
    severity: str
    ux_category: str
    ux_impact: str
    ux_penalty: int
    page_url: str
    element: str
    raw_description: str
    user_message: str
    improvement: str
    affects: str
    screenshot_path: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class UXScoreResult:
    """Complete UX scoring result."""

    ux_score: int
    risk_score: int
    ux_label: str
    risk_level: str
    ux_color: str
    total_penalty: int
    issues: list[dict[str, Any]]
    category_scores: dict[str, Any]
    top_improvements: list[dict[str, Any]]
    summary: str
    passed_checks: list[str]


def _opt_str(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    return str(v)


def _match_ux_definition(issue_type: str) -> dict[str, Any]:
    it = (issue_type or "unknown").lower().replace(" ", "_").replace("-", "_")
    if it in UX_ISSUE_DEFINITIONS:
        return UX_ISSUE_DEFINITIONS[it]
    for key, definition in UX_ISSUE_DEFINITIONS.items():
        if key in it or it in key:
            return definition
    return DEFAULT_UX_DEFINITION


def _norm_severity(s: str) -> str:
    v = (s or "").strip().lower()
    if v in {"crit", "critical", "blocker"}:
        return "critical"
    if v in {"high", "major"}:
        return "high"
    if v in {"medium", "med", "moderate"}:
        return "medium"
    if v in {"low", "minor"}:
        return "low"
    return v or "medium"


def get_max_severity(defects_in_category: list[UXIssue]) -> str:
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    best = "low"
    best_r = 0
    for d in defects_in_category:
        sev = _norm_severity(str(getattr(d, "severity", "") or ""))
        r = rank.get(sev, 0)
        if r > best_r:
            best_r = r
            best = sev
    return best


def apply_defect_penalty(base_score: float, defects_in_category: list[UXIssue]) -> float:
    if not defects_in_category:
        return base_score

    max_severity = get_max_severity(defects_in_category)
    caps = {"critical": 45, "high": 65, "medium": 82, "low": 93}
    cap = caps.get(max_severity, 100)
    return min(base_score, cap)


def score_ux(raw_issues: list[dict[str, Any]], pages_scanned: int = 1) -> UXScoreResult:
    """
    Main UX scoring function.
    Takes raw issue list from QA pipeline.
    Returns full UX score with improvements.

    Args:
        raw_issues: List of issue dicts from QA engine
        pages_scanned: Number of pages tested

    Returns:
        UXScoreResult with complete UX assessment
    """
    ux_issues: list[UXIssue] = []
    total_penalty = 0
    category_penalties: dict[str, int] = {}

    for raw in raw_issues:
        issue_type = (
            raw.get("type")
            or raw.get("issue_type")
            or raw.get("error_type")
            or raw.get("defect")
            or "unknown"
        )
        if not isinstance(issue_type, str):
            issue_type = str(issue_type)
        issue_type_norm = issue_type.lower().replace(" ", "_").replace("-", "_")

        ux_def = _match_ux_definition(issue_type_norm)

        category = str(ux_def["ux_category"])
        weight = float(CATEGORY_WEIGHTS.get(category, 1.0))
        weighted_penalty = int(int(ux_def["ux_penalty"]) * weight)

        raw_sev = raw.get("severity", "MEDIUM")
        if not isinstance(raw_sev, str):
            raw_sev = str(raw_sev)

        raw_page_url = str(raw.get("page_url") or raw.get("url") or "")
        raw_element = str(
            raw.get("element_selector")
            or raw.get("element")
            or raw.get("selector")
            or ""
        )
        raw_desc = str(raw.get("description") or raw.get("message") or "")
        raw_desc_short = raw_desc.strip().replace("\n", " ")
        if len(raw_desc_short) > 140:
            raw_desc_short = raw_desc_short[:137] + "…"

        user_message = str(ux_def["user_message"])
        improvement = str(ux_def["improvement"])
        # Avoid generic placeholders for unknown issue types.
        if (
            user_message.strip().lower().startswith("issue detected")
            or ux_def is DEFAULT_UX_DEFINITION
        ):
            user_message = f"Issue on {raw_page_url or 'unknown page'}: {raw_desc_short or issue_type_norm}"
            improvement = (
                f"Fix {raw_element or 'the affected element'} on {raw_page_url or 'the affected page'}: "
                f"{raw_desc_short or issue_type_norm}. Re-run the flow to confirm the UI/state changes as expected."
            )

        ux_issue = UXIssue(
            original_type=issue_type_norm,
            severity=raw_sev,
            ux_category=category,
            ux_impact=str(ux_def["ux_impact"]),
            ux_penalty=weighted_penalty,
            page_url=raw_page_url,
            element=raw_element,
            raw_description=raw_desc,
            user_message=user_message,
            improvement=improvement,
            affects=str(ux_def["affects"]),
            screenshot_path=_opt_str(raw.get("screenshot_path")),
            evidence=_opt_str(raw.get("evidence")),
        )
        ux_issues.append(ux_issue)

        total_penalty += weighted_penalty
        category_penalties[category] = (
            category_penalties.get(category, 0) + weighted_penalty
        )

    total_penalty = min(total_penalty, 100)

    ux_score = max(0, 100 - total_penalty)
    risk_score = 100 - ux_score

    ux_label = "CRITICAL UX ISSUES"
    ux_color = "#FF4444"
    for threshold, label, color in UX_SCORE_LABELS:
        if ux_score >= threshold:
            ux_label = label
            ux_color = color
            break

    if ux_score >= 90:
        risk_level = "LOW RISK"
    elif ux_score >= 75:
        risk_level = "LOW RISK"
    elif ux_score >= 55:
        risk_level = "MEDIUM RISK"
    elif ux_score >= 35:
        risk_level = "HIGH RISK"
    else:
        risk_level = "CRITICAL RISK"

    category_scores: dict[str, Any] = {}
    for cat in CATEGORY_WEIGHTS:
        penalty = category_penalties.get(cat, 0)
        cat_score = float(max(0, 100 - int(penalty * 1.5)))
        defects_in_category = [u for u in ux_issues if u.ux_category == cat]
        cat_score = apply_defect_penalty(cat_score, defects_in_category)
        category_scores[cat] = {
            "score": int(round(cat_score)),
            "penalty": penalty,
            "label": _score_label(int(round(cat_score))),
        }

    sorted_issues = sorted(
        ux_issues, key=lambda x: x.ux_penalty, reverse=True
    )
    top_improvements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in sorted_issues:
        imp = issue.improvement
        if imp in seen:
            continue
        seen.add(imp)
        top_improvements.append(
            {
                "priority": len(top_improvements) + 1,
                "category": issue.ux_category,
                "impact": issue.ux_impact,
                "action": issue.improvement,
                "affects": issue.affects,
                "penalty_removed": issue.ux_penalty,
            }
        )
        if len(top_improvements) >= 5:
            break

    all_categories = set(CATEGORY_WEIGHTS.keys())
    failing_categories = set(category_penalties.keys())
    passing_categories = all_categories - failing_categories
    passed_checks = [f"✓ {cat} looks good" for cat in sorted(passing_categories)]

    n_pages = max(1, int(pages_scanned) or 1)
    n_ux = len(ux_issues)
    if ux_score >= 90:
        summary = (
            f"This site delivers an excellent user experience. "
            f"All {n_pages} pages tested passed UX checks. "
            f"Users can find products, add them to cart, and "
            f"checkout without friction."
        )
    elif ux_score >= 75:
        summary = (
            f"This site has a good user experience with some "
            f"minor issues. {n_ux} issue(s) were found "
            f"that may occasionally frustrate users. "
            f"Fixing the top issues below will improve "
            f"conversion rates."
        )
    elif ux_score >= 55:
        summary = (
            f"This site has noticeable UX friction. "
            f"{n_ux} issues were found across "
            f"{n_pages} pages that are actively hurting "
            f"the user experience. Users are likely abandoning "
            f"the site before completing purchases. "
            f"Prioritize the fixes below."
        )
    elif ux_score >= 35:
        summary = (
            f"Poor user experience detected. {n_ux} "
            f"significant issues are making this site difficult "
            f"to use. Key conversion paths "
            f"(search, cart, checkout) have problems that "
            f"are directly losing sales. Immediate fixes needed."
        )
    else:
        summary = (
            f"Critical UX failures detected. {n_ux} "
            f"issues are severely breaking the user experience. "
            f"Users cannot reliably complete purchases. "
            f"This site needs urgent attention before "
            f"it can convert visitors into customers."
        )

    return UXScoreResult(
        ux_score=ux_score,
        risk_score=risk_score,
        ux_label=ux_label,
        risk_level=risk_level,
        ux_color=ux_color,
        total_penalty=total_penalty,
        issues=[_issue_to_dict(i) for i in ux_issues],
        category_scores=category_scores,
        top_improvements=top_improvements,
        summary=summary,
        passed_checks=passed_checks,
    )


def _score_label(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 55:
        return "Needs Work"
    if score >= 35:
        return "Poor"
    return "Critical"


def _issue_to_dict(issue: UXIssue) -> dict[str, Any]:
    return {
        "type": issue.original_type,
        "severity": issue.severity,
        "ux_category": issue.ux_category,
        "ux_impact": issue.ux_impact,
        "ux_penalty": issue.ux_penalty,
        "page_url": issue.page_url,
        "element": issue.element,
        "description": issue.raw_description,
        "user_message": issue.user_message,
        "improvement": issue.improvement,
        "affects": issue.affects,
        "screenshot_path": issue.screenshot_path,
        "evidence": issue.evidence,
    }
