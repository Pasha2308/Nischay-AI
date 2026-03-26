from __future__ import annotations

SUMMARY_SYSTEM_PROMPT = """You are a QA report summarizer.
Write a concise, actionable summary for engineers and PMs."""


def build_summary_prompt(results_json: str, coverage_summary: str) -> str:
    return f"""
## Results (JSON)
{results_json}

## Coverage summary
{coverage_summary or "(none)"}

Write a short summary with: overall outcome, top failures, flaky hints, next steps.
""".strip()

