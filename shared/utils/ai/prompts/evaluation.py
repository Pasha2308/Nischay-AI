from __future__ import annotations

EVALUATION_SYSTEM_PROMPT = """You are an evaluator.
Given an intent and observed page state, decide whether the intent is satisfied."""


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

