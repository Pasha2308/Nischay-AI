from __future__ import annotations

import json
import time
from pathlib import Path

from shared.models.coverage import (
    CategoryCoverage,
    CoverageRegistry,
    GlobalCoverageStats,
    PageCoverage,
    SignatureRecord,
    TestResultSummary,
)
from shared.models.site_model import SiteModel
from shared.models.test_result import RunResult


class CoverageRegistryManager:
    def __init__(self, registry_path: Path, target_url: str, history_retention: int = 20):
        self.registry_path = registry_path
        self.target_url = target_url
        self.history_retention = history_retention

    def load(self) -> CoverageRegistry:
        if not self.registry_path.exists():
            return CoverageRegistry(target_url=self.target_url)
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CoverageRegistry(**data)

    def save(self, registry: CoverageRegistry) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(registry.model_dump(), f, indent=2, default=str)

    def update_from_run(
        self,
        registry: CoverageRegistry,
        run_result: RunResult,
        site_model: SiteModel | None = None,
    ) -> CoverageRegistry:
        """Update per-page/category coverage from a run result."""
        ts = run_result.completed_at or run_result.started_at or time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Ensure pages exist in registry if we have a site model
        if site_model:
            for p in site_model.pages:
                if p.page_id not in registry.pages:
                    registry.pages[p.page_id] = PageCoverage(page_id=p.page_id, url=p.url, page_type=p.page_type)

        # Update based on test results
        for tr in run_result.test_results:
            page_id = tr.actual_page_id or tr.target_page_id
            if not page_id:
                continue

            pc = registry.pages.get(page_id)
            if pc is None:
                pc = PageCoverage(page_id=page_id, url=tr.actual_url or "", page_type="")
                registry.pages[page_id] = pc

            pc.last_tested = ts
            pc.test_count += 1

            cat = tr.category or "functional"
            if cat not in pc.categories:
                pc.categories[cat] = CategoryCoverage(category=cat)
            cc = pc.categories[cat]

            sig = tr.coverage_signature or ""
            if sig:
                rec = next((r for r in cc.signatures_tested if r.signature == sig), None)
                if rec is None:
                    rec = SignatureRecord(signature=sig)
                    cc.signatures_tested.append(rec)
                rec.last_tested = ts
                rec.last_result = tr.result
                rec.test_count += 1
                rec.history.append(
                    TestResultSummary(
                        run_id=run_result.run_id,
                        timestamp=ts,
                        result=tr.result,
                        duration_seconds=tr.duration_seconds or 0.0,
                        failure_reason=tr.failure_reason,
                    )
                )
                rec.history = rec.history[-self.history_retention :]

        self._recompute_global_stats(registry)
        return registry

    @staticmethod
    def _recompute_global_stats(registry: CoverageRegistry) -> None:
        gs = GlobalCoverageStats()
        gs.total_pages = len(registry.pages)
        gs.pages_tested = sum(1 for p in registry.pages.values() if p.last_tested)

        # Category scores: naive percent of pages with at least one signature in that category
        cat_pages: dict[str, int] = {}
        cat_total: dict[str, int] = {}
        for p in registry.pages.values():
            for cat, cc in p.categories.items():
                cat_total[cat] = cat_total.get(cat, 0) + 1
                if cc.signatures_tested:
                    cat_pages[cat] = cat_pages.get(cat, 0) + 1

        for cat, total in cat_total.items():
            gs.category_scores[cat] = (cat_pages.get(cat, 0) / total) if total else 0.0

        gs.overall_score = (gs.pages_tested / gs.total_pages) if gs.total_pages else 0.0
        registry.global_stats = gs

