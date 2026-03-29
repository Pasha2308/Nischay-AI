from __future__ import annotations

import json
from typing import Any

EVALUATION_SYSTEM_PROMPT = """You are an evaluator.
Given an intent and observed page state, decide whether the intent is satisfied."""

# Step-level evaluator (Executor): reasoning-first, structured JSON.
EVALUATOR_STEP_SYSTEM_PROMPT = """You are an expert QA evaluator for browser automation steps.
Your job is to reason about whether a step achieved its intended outcome — not to apply rigid if/then rules.

For every step, explicitly consider:
- Expected outcome: what success looks like for this step in context of the scan goal
- Action performed: what the automation attempted
- Observed result: pass/fail signals, errors, DOM or assertion hints in the payload
- Context: URL after the step and step type (click, navigate, fill, etc.)

You MUST respond with ONLY a single JSON object. No markdown code fences, no prose before or after.

Required schema (all keys required):
{
  "success": boolean,
  "confidence": number,
  "reason": string,
  "should_retry": boolean
}

Definitions:
- "success": true only if the evidence shows the step met the expected outcome; false if it did not or evidence is insufficient.
- "confidence": calibrated 0.0–1.0. Use below 0.6 when ambiguous, partial success, possible flake, or thin evidence. Low confidence implies uncertainty worth another attempt.
- "reason": concise factual judgment citing expected vs observed.
- "should_retry": answer exactly: "Should this be retried with a different strategy?" True if different timing, selector, scroll, wait, navigation order, or retry could plausibly help; true if uncertain; false if failure is definitive or retry cannot help.

Do not include keys other than the four above."""


def build_evaluator_system_prompt(scan_task: str = "full_app") -> str:
    """System prompt for EvaluatorAgent: scan goal + reasoning instructions."""
    task = (scan_task or "").strip() or "full_app"
    return f"""## Scan / task goal
Use this when interpreting whether a step succeeded: {task}

{EVALUATOR_STEP_SYSTEM_PROMPT}"""


def build_step_evaluation_user_prompt(
    *,
    expected_outcome: str,
    action_performed: str,
    actual_result: dict[str, Any],
    page_url: str,
    step_type: str,
    test_id: str = "",
) -> str:
    """Rich context for step evaluation (LLM)."""
    test_line = f"Test / case id: {test_id}\n" if test_id else ""
    return f"""{test_line}## Expected outcome
{expected_outcome or "(none specified)"}

## Action performed
{action_performed or "(unknown)"}

## Step type (context)
{step_type}

## Context — URL after step
{page_url or "(unknown)"}

## Observed result
{json.dumps(actual_result, ensure_ascii=False, indent=2, default=str)}

## Your decisions (encode in JSON only)
1. Did this step satisfy the expected outcome given the evidence?
2. Should this be retried with a different strategy (timing, selector, navigation, wait)?

Emit a single JSON object with keys success, confidence, reason, should_retry — no other text."""


def build_evaluation_prompt(intent: str, current_url: str, page_text: str) -> str:
    return f"""
## Intent
{intent}

## Current URL
{current_url}

## Visible text (truncated)
{(page_text or '')[:5000]}

Return ONLY JSON: {{ passed: boolean, confidence: number, reasoning: string }}.
""".strip()

