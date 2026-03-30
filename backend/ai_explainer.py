"""Optional Claude-based explanation for QA issues (Anthropic API)."""

from __future__ import annotations

import json
import os
from typing import Any


MODEL = "claude-sonnet-4-20250514"


async def explain_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Return structured explanation or {ai_available: false} on failure."""
    try:
        from anthropic import AsyncAnthropic
    except Exception:
        return {
            "ai_available": False,
            "executive_summary": "AI explainer unavailable (anthropic package missing).",
            "issues_explained": [],
            "raw_issues": issues,
        }

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {
            "ai_available": False,
            "executive_summary": "Set ANTHROPIC_API_KEY to enable AI explanations.",
            "issues_explained": [],
            "raw_issues": issues,
        }

    client = AsyncAnthropic(api_key=key)
    payload = json.dumps(issues[:80], indent=2, default=str)[:48_000]
    prompt = (
        "You are a senior QA lead. Given the following JSON list of detected issues, produce:\n"
        "1) A short executive_summary in plain English for stakeholders.\n"
        "2) For each issue (or grouped by theme if many), explain business_impact and suggested priority.\n"
        "Respond with STRICT JSON only, no markdown, in this shape:\n"
        '{"executive_summary": string, "issues_explained": ['
        '{"original_issue": object, "plain_english": string, "business_impact": string, "priority": string}'
        "]}\n\nISSUES_JSON:\n"
        + payload
    )

    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            temperature=0.2,
            system="You output only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in getattr(resp, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                text += t
        data = json.loads(text.strip())
        data["ai_available"] = True
        return data
    except Exception as e:
        return {
            "ai_available": False,
            "executive_summary": f"AI call failed: {e}",
            "issues_explained": [],
            "raw_issues": issues,
        }
