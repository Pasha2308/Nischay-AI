from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.models.coverage import CoverageGapReport, CoverageRegistry
from shared.models.site_model import SiteModel


def analyze_gaps(
    registry: CoverageRegistry,
    site_model: SiteModel,
    staleness_threshold_days: int,
) -> CoverageGapReport:
    """Very lightweight gap analysis to keep planner usable."""
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(days=staleness_threshold_days)

    untested_pages: list[str] = []
    stale_pages: list[str] = []

    for p in site_model.pages:
        cov = registry.pages.get(p.page_id)
        if not cov or not cov.last_tested:
            untested_pages.append(p.url)
            continue
        try:
            last = datetime.fromisoformat(cov.last_tested.replace("Z", "+00:00"))
            if last < stale_before:
                stale_pages.append(p.url)
        except Exception:
            pass

    suggested_focus = []
    if untested_pages:
        suggested_focus.append("Cover untested pages first.")
    if stale_pages:
        suggested_focus.append("Refresh stale coverage areas.")

    return CoverageGapReport(
        untested_pages=untested_pages,
        stale_pages=stale_pages,
        suggested_focus=suggested_focus,
    )

