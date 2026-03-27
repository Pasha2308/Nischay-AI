"""Pipeline orchestrator — deterministic smoke flow (no AI dependency)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from backend.crawler.crawler import Crawler
from backend.deterministic_plan import build_deterministic_smoke_plan
from backend.executor.executor import Executor
from backend.reporter.reporter import Reporter
from backend.structured_run_output import build_structured_output
from shared.models.config import FrameworkConfig
from shared.models.site_model import SiteModel
from shared.models.test_plan import TestPlan
from shared.models.test_result import RunResult
from shared.utils.coverage.registry import CoverageRegistryManager
from shared.utils.coverage.visual_baseline_registry import VisualBaselineRegistryManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates crawl → deterministic plan → execute (+ optional report/coverage)."""

    def __init__(self, config: FrameworkConfig):
        self.config = config
        self.framework_dir = Path(".qa-framework")
        self.framework_dir.mkdir(exist_ok=True)
        self.runs_dir = Path("runs")
        self.runs_dir.mkdir(exist_ok=True)

        # No AI for now — executor/planner AI paths stay inert.
        self.ai_client = None

        self.registry_manager = CoverageRegistryManager(
            registry_path=self.framework_dir / "coverage" / "registry.json",
            target_url=config.target_url,
            history_retention=config.history_retention_runs,
        )

        self.visual_baseline_manager = VisualBaselineRegistryManager(
            registry_path=self.framework_dir / "visual_baselines" / "registry.json",
            baselines_dir=self.framework_dir / "visual_baselines",
            target_url=config.target_url,
        )
        self._last_site_model: SiteModel | None = None
        self._last_run_result: RunResult | None = None
        self._started_at: float = time.time()

    def run_full_pipeline(self) -> dict:
        """Execute the pipeline and return structured JSON (always, even on failure)."""
        return asyncio.run(self._run_pipeline())

    async def _run_pipeline(self) -> dict:
        start = time.time()
        self._started_at = start
        site_model: SiteModel | None = None
        run_result: RunResult | None = None
        reports: dict[str, str] = {}
        registry_summary: dict = {}

        logger.info("=== Starting deterministic pipeline (no AI) for %s ===", self.config.target_url)

        try:
            # Stage 1: Crawl
            logger.info("--- Stage 1: Crawl ---")
            t0 = time.time()
            site_model = await self._crawl()
            self._last_site_model = site_model
            self._save_site_model(site_model)
            logger.info(
                "--- Stage 1 complete: %d pages in %.1fs ---",
                len(site_model.pages),
                time.time() - t0,
            )

            # Stage 2: Deterministic plan
            logger.info("--- Stage 2: Deterministic plan ---")
            t0 = time.time()
            plan = self._deterministic_plan(site_model)
            self._save_plan(plan)
            logger.info(
                "--- Stage 2 complete: %d test cases in %.1fs ---",
                len(plan.test_cases),
                time.time() - t0,
            )

            # Stage 3: Execute (tool-based executor)
            logger.info("--- Stage 3: Execute ---")
            t0 = time.time()
            run_result = await self._execute(plan)
            self._last_run_result = run_result
            self._save_run_result(run_result)
            logger.info(
                "--- Stage 3 complete: %d passed, %d failed in %.1fs ---",
                run_result.passed,
                run_result.failed,
                time.time() - t0,
            )

            # Stage 4: Coverage (best-effort)
            try:
                logger.info("--- Stage 4: Coverage ---")
                registry = self.registry_manager.load()
                registry = self.registry_manager.update_from_run(
                    registry, run_result, site_model=site_model
                )
                self.registry_manager.save(registry)
                registry_summary = {
                    "overall": registry.global_stats.overall_score,
                    "categories": registry.global_stats.category_scores,
                }
            except Exception as e:
                logger.warning("Coverage update skipped: %s", e)
                registry_summary = {}

            # Stage 5: Reports (best-effort, no AI summary)
            try:
                logger.info("--- Stage 5: Report ---")
                previous_run = self._load_previous_run_result(run_result.run_id)
                registry = self.registry_manager.load()
                reports = self._report(run_result, registry, previous_run=previous_run)
            except Exception as e:
                logger.warning("Report generation skipped: %s", e)

        except Exception as e:
            logger.exception("Pipeline failed: %s", e)
            duration = round(time.time() - start, 2)
            return build_structured_output(
                site_model=site_model,
                run_result=run_result,
                pipeline_error=str(e),
                extra={
                    "run_id": run_result.run_id if run_result else None,
                    "duration": duration,
                    "mode": "deterministic_no_ai",
                    "results": None,
                    "coverage": registry_summary,
                    "reports": reports,
                },
            )

        duration = round(time.time() - start, 2)
        extra = {
            "run_id": run_result.run_id if run_result else None,
            "duration": duration,
            "mode": "deterministic_no_ai",
            "results": {
                "total": run_result.total_tests,
                "passed": run_result.passed,
                "failed": run_result.failed,
                "skipped": run_result.skipped,
                "errors": run_result.errors,
            }
            if run_result
            else None,
            "coverage": registry_summary,
            "reports": reports,
        }
        return build_structured_output(
            site_model=site_model,
            run_result=run_result,
            pipeline_error=None,
            extra=extra,
        )

    def build_partial_result(self, warning_message: str) -> dict[str, object]:
        duration = round(time.time() - self._started_at, 2)
        return build_structured_output(
            site_model=self._last_site_model,
            run_result=self._last_run_result,
            pipeline_error=None,
            extra={
                "run_id": self._last_run_result.run_id if self._last_run_result else None,
                "duration": duration,
                "mode": "deterministic_no_ai",
                "status": "partial",
                "warning": warning_message,
            },
        )

    async def _crawl(self) -> SiteModel:
        site_model_dir = self.framework_dir / "site_model"
        crawler = Crawler(self.config, site_model_dir, ai_client=None)
        return await crawler.crawl()

    def run_crawl_only(self) -> SiteModel:
        return asyncio.run(self._crawl())

    def _deterministic_plan(self, site_model: SiteModel) -> TestPlan:
        return build_deterministic_smoke_plan(self.config, site_model)

    def run_plan_only(self) -> TestPlan:
        site_model = self._load_site_model()
        return self._deterministic_plan(site_model)

    async def _execute(self, plan: TestPlan) -> RunResult:
        baseline_dir = self.framework_dir / "site_model" / "baselines"
        visual_registry = self.visual_baseline_manager.load()
        executor = Executor(
            self.config,
            None,
            self.runs_dir,
            visual_registry=visual_registry,
            visual_registry_manager=self.visual_baseline_manager,
        )
        result = await executor.execute(plan, baseline_dir if baseline_dir.exists() else None)
        self.visual_baseline_manager.save(visual_registry)
        return result

    def run_execute_only(self, plan: TestPlan) -> RunResult:
        return asyncio.run(self._execute(plan))

    def _report(
        self,
        run_result: RunResult,
        registry=None,
        previous_run: RunResult | None = None,
    ) -> dict[str, str]:
        reporter = Reporter(self.config, None)
        return reporter.generate_reports(
            run_result,
            registry,
            previous_run=previous_run,
            output_dir=Path(self.config.report_output_dir),
        )

    def _save_site_model(self, model: SiteModel) -> None:
        path = self.framework_dir / "site_model" / "model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(model.model_dump(), f, indent=2, default=str)

    def _load_site_model(self) -> SiteModel:
        path = self.framework_dir / "site_model" / "model.json"
        if not path.exists():
            raise FileNotFoundError("No site model found. Run crawl first.")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return SiteModel(**data)

    def _save_plan(self, plan: TestPlan) -> None:
        path = self.framework_dir / "latest_plan.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, indent=2, default=str)

    def _save_run_result(self, run_result: RunResult) -> None:
        path = self.runs_dir / run_result.run_id / "run_result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(run_result.model_dump(), f, indent=2, default=str)

    def _load_previous_run_result(self, current_run_id: str) -> RunResult | None:
        report_dir = Path(self.config.report_output_dir)
        if not report_dir.exists():
            return None
        report_files = sorted(
            report_dir.glob("report_run_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for report_path in report_files:
            try:
                with open(report_path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("run_id") == current_run_id:
                    continue
                return RunResult.model_validate(data)
            except Exception as e:
                logger.debug("Could not load previous run from %s: %s", report_path, e)
        return None
