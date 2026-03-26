from __future__ import annotations

PLANNING_SYSTEM_PROMPT = """You are an expert QA engineer.
Generate a structured JSON test plan for the given site model and constraints."""


def build_planning_prompt(
    site_model_json: str,
    coverage_gaps_json: str,
    config_summary: str,
    hints: list[str] | None,
    max_tests: int,
) -> str:
    hints_text = "\n".join(f"- {h}" for h in (hints or [])) or "(none)"
    return f"""
## Config
{config_summary}

## Hints
{hints_text}

## Coverage gaps (may be empty)
{coverage_gaps_json}

## Site model (summarized)
{site_model_json}

Return ONLY valid JSON with keys: plan_id, generated_at, test_cases[] (bounded to {max_tests}).
""".strip()

