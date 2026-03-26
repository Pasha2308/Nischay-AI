from __future__ import annotations

FALLBACK_SYSTEM_PROMPT = """You are a test execution assistant.
Given a failing selector/action, propose a safe retry selector or adapted action."""


def build_fallback_prompt(
    test_context: str,
    dom_snippet: str,
    console_errors: list[str] | None,
    original_action_json: str,
) -> str:
    errors = "\n".join(console_errors or [])[-2000:] if console_errors else "(none)"
    return f"""
## Context
{test_context}

## Console errors (tail)
{errors}

## DOM snippet (truncated)
{dom_snippet[:3000]}

## Original action (JSON)
{original_action_json}

Return ONLY JSON: {{ decision: retry|adapt|abort, new_selector?: string, reasoning: string, new_action?: object }}.
""".strip()

