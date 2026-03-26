"""Deterministic smoke test plan (no AI).

Steps:
1. Open target URL
2. If login form is detected, execute auth-like flow
3. Else run generic interaction flow (button + input)

Uses selectors that resolve to the first matching element in Playwright.
"""

from __future__ import annotations

import time
import uuid

from shared.models.config import FrameworkConfig
from shared.models.site_model import SiteModel
from shared.models.test_plan import Action, Assertion, TestCase, TestPlan
from shared.utils.url_utils import page_id_from_url


# First visible real <button> (document order). Minimal, widely supported selector.
_BUTTON_SELECTOR = (
    "button:visible, "
    "input[type='submit']:visible, "
    "input[type='button']:visible, "
    "[role='button']:visible, "
    "a[role='button']:visible"
)

# First visible text field or textarea.
_INPUT_SELECTOR = "input[type='text']:visible, input:not([type]):visible, textarea:visible"
_LOGIN_EMAIL_SELECTOR = "input[type='email']:visible, input[name*='email' i]:visible"
_LOGIN_PASSWORD_SELECTOR = "input[type='password']:visible, input[name*='pass' i]:visible"
_LOGIN_SUBMIT_SELECTOR = (
    "button[type='submit']:visible, "
    "input[type='submit']:visible, "
    "button:has-text('Log in'):visible, "
    "button:has-text('Login'):visible, "
    "button:has-text('Sign in'):visible, "
    "[role='button'][aria-label*='login' i]:visible"
)


def _has_login_form(site_model: SiteModel) -> bool:
    for page in site_model.pages:
        # Strong signal: form fields modeled by crawler
        for form in page.forms:
            field_types = {f.field_type.lower() for f in form.fields}
            if "password" in field_types and ("email" in field_types or "text" in field_types):
                return True

        # Fallback signal: extracted element metadata
        for el in page.elements:
            attrs = {k.lower(): (v or "").lower() for k, v in el.attributes.items()}
            if attrs.get("type") == "password":
                return True
    return False


def build_deterministic_smoke_plan(config: FrameworkConfig, site_model: SiteModel) -> TestPlan:
    """Single test case targeting the configured URL; no auth required."""
    target = (config.target_url or site_model.base_url or "").strip()
    if not target:
        raise ValueError("target_url is required")

    page_id = page_id_from_url(target)
    plan_id = f"plan_det_{uuid.uuid4().hex[:8]}"
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    flow_type = "generic_flow"
    steps: list[Action] = [
        Action(action_type="navigate", value=target, description="Open target page"),
        Action(action_type="wait", value="900", description="Settle after navigation"),
    ]

    if _has_login_form(site_model):
        flow_type = "auth_flow"
        steps.extend(
            [
                Action(
                    action_type="fill",
                    selector=_LOGIN_EMAIL_SELECTOR,
                    value="test@example.com",
                    description="Fill login email",
                ),
                Action(
                    action_type="fill",
                    selector=_LOGIN_PASSWORD_SELECTOR,
                    value="Test@123",
                    description="Fill login password",
                ),
                Action(
                    action_type="click",
                    selector=_LOGIN_SUBMIT_SELECTOR,
                    description="Click login/submit button",
                ),
                Action(
                    action_type="wait",
                    value="1200",
                    description="Wait for post-login navigation",
                ),
            ]
        )
    else:
        steps.extend(
            [
                Action(
                    action_type="click",
                    selector=_BUTTON_SELECTOR,
                    description="Click visible primary action if present",
                ),
                Action(
                    action_type="fill",
                    selector=_INPUT_SELECTOR,
                    value="{{synthetic}}",
                    description="Fill first visible text input if present",
                ),
            ]
        )

    assertions = [
        Assertion(
            assertion_type="page_loaded",
            description="Page has basic content after steps",
        ),
    ]

    tc = TestCase(
        test_id="deterministic_smoke",
        name=f"Deterministic smoke ({flow_type})",
        description="No-AI deterministic flow using tool-based executor.",
        category="functional",
        priority=1,
        target_page_id=page_id,
        coverage_signature=f"deterministic_smoke_{flow_type}_v1",
        requires_auth=False,
        preconditions=[],
        steps=steps,
        assertions=assertions,
        timeout_seconds=max(60, config.selector_timeout_seconds * 3),
    )

    return TestPlan(
        plan_id=plan_id,
        generated_at=generated_at,
        target_url=target,
        test_cases=[tc],
        estimated_duration_seconds=60,
        coverage_intent={"mode": "deterministic_smoke", "no_ai": True, "flow_type": flow_type},
    )
