from __future__ import annotations

from shared.models.coverage import CoverageRegistry


def calculate_coverage_summary(registry: CoverageRegistry) -> str:
    """Human-readable summary used in reports."""
    gs = registry.global_stats
    cat = ", ".join(f"{k}={v:.0%}" for k, v in (gs.category_scores or {}).items()) or "(none)"
    return (
        f"Overall coverage: {gs.overall_score:.0%}. "
        f"Pages tested: {gs.pages_tested}/{gs.total_pages}. "
        f"Category scores: {cat}."
    )

