"""
Release decision from micro-task outcomes (impact- and journey-based rules).
"""

from __future__ import annotations

from typing import Any

# Tasks treated as cart / checkout critical path for shipping gate
_CART_TASKS = frozenset({"add_to_cart"})
_CHECKOUT_TASKS = frozenset(
    {
        "start_checkout",
        "fill_address_form",
        "place_order_attempt",
    }
)


def generate_decision(task_results: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Derive a ship / no-ship style decision from per-task results.

    Each item may include: ``task``, ``success`` (bool), ``impact`` (LOW|MEDIUM|HIGH).

    ``risk_score`` (0–100) sums weighted points for **failed** tasks only:
    HIGH +40, MEDIUM +20, LOW +10.
    """
    rows: list[dict[str, Any]] = list(task_results) if task_results else []

    high_impact_failures = 0
    total_failures = 0
    medium_failures = 0
    cart_or_checkout_failed = False
    risk_score = 0

    for r in rows:
        if not isinstance(r, dict):
            continue
        task = str(r.get("task") or "").strip()
        success = r.get("success", True)
        impact = str(r.get("impact") or "LOW").strip().upper()
        if impact not in ("LOW", "MEDIUM", "HIGH"):
            impact = "LOW"

        failed = success is False
        if failed:
            total_failures += 1
            if impact == "HIGH":
                high_impact_failures += 1
                risk_score += 40
            elif impact == "MEDIUM":
                medium_failures += 1
                risk_score += 20
            else:
                risk_score += 10
            if task in _CART_TASKS or task in _CHECKOUT_TASKS:
                cart_or_checkout_failed = True

    risk_score = min(100, int(risk_score))

    if cart_or_checkout_failed:
        decision = "DO NOT SHIP"
        risk = "HIGH"
    elif medium_failures >= 2:
        decision = "CAUTION"
        risk = "MEDIUM"
    else:
        decision = "SAFE TO SHIP"
        risk = "LOW"

    summary = (
        f"{high_impact_failures} high-impact task failure(s), "
        f"{total_failures} total task failure(s), "
        f"{medium_failures} medium-impact failure(s). "
        f"Numeric risk score: {risk_score}/100."
    )

    return {
        "decision": decision,
        "risk": risk,
        "risk_score": risk_score,
        "summary": summary,
    }
