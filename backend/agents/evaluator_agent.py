"""Step evaluator: LLM-first reasoning when configured; rules as fallback."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from backend.services.llm_client import LLMClient, _is_placeholder_api_key
from shared.utils.ai.prompts.evaluation import (
    build_evaluator_system_prompt,
    build_step_evaluation_user_prompt,
)

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _llm_configured() -> bool:
    """Match LLMClient.complete requirements (key + model + base URL)."""
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    if not key or _is_placeholder_api_key(key):
        return False
    if not (os.environ.get("LLM_MODEL") or "").strip():
        return False
    if not (os.environ.get("LLM_BASE_URL") or "").strip():
        return False
    return True


def _confidence_threshold() -> float:
    """Below this, force should_retry (ambiguous / uncertain judgments)."""
    raw = (os.environ.get("EVALUATOR_CONFIDENCE_THRESHOLD") or "").strip()
    if not raw:
        return 0.55
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.55


def _rule_based_evaluate(expected_outcome: str, actual_result: dict[str, Any]) -> dict[str, Any]:
    """Classify outcome without LLM (fallback)."""
    a = actual_result

    if a.get("action_failed") is True:
        return {
            "success": False,
            "confidence": 1.0,
            "reason": "Action failed (explicit flag).",
            "should_retry": True,
        }
    step_status = (a.get("step_status") or a.get("status") or "").lower()
    if step_status == "fail":
        return {
            "success": False,
            "confidence": 1.0,
            "reason": "Step or action reported failure.",
            "should_retry": True,
        }

    if a.get("assertion_failed") is True:
        return {
            "success": False,
            "confidence": 1.0,
            "reason": "Assertion failed.",
            "should_retry": False,
        }
    if a.get("passed") is False or a.get("assertion_passed") is False:
        return {
            "success": False,
            "confidence": 1.0,
            "reason": "Assertion did not pass.",
            "should_retry": False,
        }

    err = a.get("error")
    if err:
        return {
            "success": False,
            "confidence": 0.85,
            "reason": f"Error present: {err}",
            "should_retry": True,
        }

    return {
        "success": True,
        "confidence": 0.8,
        "reason": "No failure signals in actual result.",
        "should_retry": False,
    }


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    raw = _JSON_FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _normalize_eval_dict(data: dict[str, Any]) -> dict[str, Any]:
    success = bool(data.get("success", False))
    conf = data.get("confidence", 0.5)
    try:
        confidence = float(conf)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get("reason") or "").strip() or "No reason provided."
    should_retry = bool(data.get("should_retry", False))
    # Alternate keys some models may emit
    if not should_retry:
        if data.get("retry_with_different_strategy") is not None:
            should_retry = bool(data.get("retry_with_different_strategy"))
        elif data.get("retry") is not None:
            should_retry = bool(data.get("retry"))
    # Explicit retry recommendation (some JSON schemas)
    if data.get("should_retry_with_different_strategy") is not None:
        should_retry = should_retry or bool(data.get("should_retry_with_different_strategy"))
    return {
        "success": success,
        "confidence": confidence,
        "reason": reason,
        "should_retry": should_retry,
    }


def _apply_confidence_threshold(result: dict[str, Any]) -> dict[str, Any]:
    """Low model confidence → retry (uncertainty / flaky outcome)."""
    th = _confidence_threshold()
    conf = float(result.get("confidence", 0.0))
    out = dict(result)
    if conf < th:
        out["should_retry"] = True
    return out


def _eval_schema_ok(d: dict[str, Any]) -> bool:
    return all(k in d for k in ("success", "confidence", "reason", "should_retry"))


class EvaluatorAgent:
    """Evaluates whether a step matched the expected outcome (LLM-first when configured)."""

    def __init__(self, scan_task: str = "full_app") -> None:
        self.scan_task = scan_task
        self._llm: LLMClient | None = None

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    async def evaluate_step(
        self,
        expected_outcome: str,
        actual_result: dict[str, Any],
        *,
        page_url: str = "",
        action_performed: str = "",
        step_type: str = "test_step",
        test_id: str = "",
    ) -> dict[str, Any]:
        """Return success, confidence, reason, should_retry (structured). LLM-first when configured."""
        def _fallback() -> dict[str, Any]:
            b = _rule_based_evaluate(expected_outcome, actual_result)
            return _apply_confidence_threshold(b)

        if not _llm_configured():
            return _fallback()

        user_prompt = build_step_evaluation_user_prompt(
            expected_outcome=expected_outcome,
            action_performed=action_performed,
            actual_result=actual_result,
            page_url=page_url,
            step_type=step_type,
            test_id=test_id,
        )
        system_prompt = build_evaluator_system_prompt(self.scan_task)

        try:
            llm = self._get_llm()
            text = await llm.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                fast=True,
                json_mode=True,
            )
            parsed = _parse_llm_json(text or "")
            if parsed is None:
                logger.warning("Evaluator LLM returned non-JSON; using rule fallback")
                return _fallback()

            merged = _normalize_eval_dict(parsed)
            if not _eval_schema_ok(merged):
                logger.warning("Evaluator LLM JSON incomplete; using rule fallback")
                return _fallback()

            return _apply_confidence_threshold(merged)
        except Exception as e:
            logger.warning("Evaluator LLM call failed: %s; using rule fallback", e)
            return _fallback()
