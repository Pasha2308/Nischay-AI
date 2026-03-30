"""Centralized risk score weights and level mapping for Nischay AI / QA pipeline.

All severity → numeric weights and aggregate risk_level must use this module only.
"""

from __future__ import annotations

# Weights per severity (single source of truth).
WEIGHT_CRITICAL = 100
WEIGHT_HIGH = 70
WEIGHT_MEDIUM = 40
WEIGHT_LOW = 10


def normalize_severity(raw: str | None) -> str:
    s = (raw or "medium").strip().lower()
    if s in ("critical", "crit", "sev1", "blocker"):
        return "critical"
    if s in ("high", "error", "errors"):
        return "high"
    if s in ("medium", "med", "warn", "warning", "moderate"):
        return "medium"
    if s in ("low", "info", "note", "minor"):
        return "low"
    return "medium"


def risk_weight(severity: str) -> int:
    """Map normalized severity to numeric weight."""
    match normalize_severity(severity):
        case "critical":
            return WEIGHT_CRITICAL
        case "high":
            return WEIGHT_HIGH
        case "medium":
            return WEIGHT_MEDIUM
        case "low":
            return WEIGHT_LOW
        case _:
            return WEIGHT_MEDIUM


def risk_level_from_score(score: int) -> str:
    """Aggregate label from summed weights (handles any positive score)."""
    s = max(0, int(score))
    if s > 200:
        return "HIGH RISK"
    if s > 100:
        return "MEDIUM RISK"
    return "LOW RISK"
