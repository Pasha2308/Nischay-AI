"""Pipeline orchestrator — deterministic smoke flow (no AI dependency)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from backend.models.action_log import (
    new_action_record,
    should_capture_before_after_pair,
    should_capture_error_after_screenshot,
)

_T = TypeVar("_T")

from backend.core.browser import launch_browser
from backend.core.context import create_context
from backend.core.task_intent import extract_search_query_from_task_input
from backend.core.decision_engine import generate_decision
from backend.core.ecommerce_plan import expand_selected_flows, run_ecommerce_scan, run_micro_task
from backend.core.task_registry import TASK_REGISTRY
from backend.core.login_handler import handle_login
from backend.crawler.crawler import Crawler
from backend.deterministic_plan import build_deterministic_smoke_plan
from backend.reporter.reporter import Reporter
from backend.services.decision_insights import attach_decision_insights
from backend.services.risk_explanation import attach_risk_explanation
from backend.structured_run_output import build_structured_output, site_pages_payload
from shared.models.config import FrameworkConfig
from shared.models.site_model import AuthFlow, PageModel, SiteModel
from shared.utils.auth import perform_smart_auth
from shared.utils.browser_stealth import create_stealth_context
from shared.models.test_plan import TestPlan
from shared.models.test_result import RunResult, TestResult
from shared.utils.url_utils import page_id_from_url
from shared.pipeline_emit import PipelineEmit
from shared.utils.coverage.registry import CoverageRegistryManager
from shared.utils.coverage.visual_baseline_registry import VisualBaselineRegistryManager

logger = logging.getLogger(__name__)

# Pipeline phase banners (streamed to API / live log)
PHASE_1_CRAWLING = "━━━ PHASE 1: CRAWLING ━━━"
PHASE_2_EXECUTION = "━━━ PHASE 2: EXECUTION ━━━"
PHASE_3_AI_ANALYSIS = "━━━ PHASE 3: AI ANALYSIS ━━━"
PHASE_4_REPORT = "━━━ PHASE 4: REPORT ━━━"


def _build_execution_snapshot(
    *,
    page_url: str,
    defects: list[Any],
    results: dict[str, Any],
    task_type: str,
    logs: list[str],
    duration_seconds: float,
) -> dict[str, Any]:
    """Stable shape for frontend: decision from decision_engine; task_results from scan (or single micro task)."""
    task_results: list[dict[str, Any]] = list(results.get("task_results") or [])
    if not task_results and task_type == "micro":
        r = (results.get("metrics") or {}).get("result")
        if isinstance(r, dict):
            task_results = [r]
    dec = generate_decision(task_results)
    return {
        "url": page_url,
        "decision": dec["decision"],
        "risk": dec["risk"],
        "risk_score": int(dec.get("risk_score", 0)),
        "summary": dec["summary"],
        "task_results": task_results,
        "defects": list(defects),
        "logs": list(logs),
        "duration": round(float(duration_seconds), 2),
    }


def _minimal_site_model_for_target(target_url: str) -> SiteModel:
    """Single synthetic page for reporting/plan when crawl is skipped (micro-task execution only)."""
    t = (target_url or "").strip()
    if not t:
        raise ValueError("target_url is required")
    pid = page_id_from_url(t)
    return SiteModel(
        base_url=t,
        pages=[PageModel(page_id=pid, url=t, page_type="static", title="")],
    )


class Orchestrator:
    """Coordinates optional crawl → deterministic plan → execute (+ optional report/coverage)."""

    def __init__(
        self,
        config: FrameworkConfig,
        emit: PipelineEmit | None = None,
        *,
        job_id: str | None = None,
    ):
        self.config = config
        self._pipeline_emit = emit
        self._action_job_id = (job_id or "").strip() or None
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
        self.action_trail: list[dict[str, Any]] = []
        self._session_id: str = ""

    def _screenshot_dir(self) -> Path:
        return Path("screenshots") / self._session_id

    def _login_nav_url(self) -> str:
        creds = self.config.credentials or {}
        lu = str(creds.get("login_url") or "").strip()
        return lu or self.config.target_url

    async def log_action_bracketed(
        self,
        page: Page | None,
        *,
        phase: str,
        action_type: str,
        description: str,
        coro: Callable[[], Awaitable[_T]],
        target_url: str = "",
        target_element: str = "",
        input_value: str | None = None,
    ) -> _T:
        """Run ``coro`` with optional before/after screenshots for navigate/click/submit; errors get after shot."""
        aid = str(uuid.uuid4())
        root = self._screenshot_dir()
        before_path = ""
        after_path = ""
        pair = bool(page) and should_capture_before_after_pair(action_type)
        t0 = time.perf_counter()
        outcome = "success"
        detail = ""
        result: _T | None = None
        try:
            if pair:
                root.mkdir(parents=True, exist_ok=True)
                before_path = str(root / f"{aid}_before.png")
                await page.screenshot(path=before_path, full_page=False)  # type: ignore[union-attr]
            result = await coro()
        except Exception as e:
            outcome = "failed"
            detail = str(e)[:500]
            raise
        finally:
            dur = int((time.perf_counter() - t0) * 1000)
            tu = target_url
            if not tu and page is not None:
                try:
                    tu = page.url or ""
                except Exception:
                    tu = ""
            take_after = bool(page) and (
                pair or should_capture_error_after_screenshot(outcome)
            )
            if take_after:
                root.mkdir(parents=True, exist_ok=True)
                after_path = str(root / f"{aid}_after.png")
                try:
                    await page.screenshot(path=after_path, full_page=False)  # type: ignore[union-attr]
                except Exception as e:
                    logger.debug("Action after screenshot failed: %s", e)
                    after_path = ""
            rec = new_action_record(
                phase=phase,
                action_type=action_type,
                description=description,
                target_url=tu,
                target_element=target_element,
                input_value=input_value,
                outcome=outcome,
                outcome_detail=detail,
                screenshot_path_before=before_path,
                screenshot_path_after=after_path,
                duration_ms=dur,
                action_id=aid,
            )
            self.action_trail.append(rec.to_dict())
        return result  # type: ignore[return-value]

    async def log_action(
        self,
        page: Page | None,
        *,
        phase: str,
        action_type: str,
        description: str,
        target_url: str = "",
        target_element: str = "",
        input_value: str | None = None,
        outcome: str = "success",
        outcome_detail: str = "",
        duration_ms: int = 0,
        defect_triggered: str | None = None,
    ) -> str:
        """Append an ActionRecord. Screenshots only for error outcomes (after-only)."""
        aid = str(uuid.uuid4())
        before_path = ""
        after_path = ""
        if page is not None and should_capture_error_after_screenshot(outcome):
            try:
                root = self._screenshot_dir()
                root.mkdir(parents=True, exist_ok=True)
                after_path = str(root / f"{aid}_after.png")
                await page.screenshot(path=after_path, full_page=False)
            except Exception as e:
                logger.debug("Action error screenshot failed: %s", e)
                after_path = ""
        tu = target_url
        if not tu and page is not None:
            try:
                tu = page.url or ""
            except Exception:
                tu = ""
        rec = new_action_record(
            phase=phase,
            action_type=action_type,
            description=description,
            target_url=tu,
            target_element=target_element,
            input_value=input_value,
            outcome=outcome,
            outcome_detail=outcome_detail,
            screenshot_path_before=before_path,
            screenshot_path_after=after_path,
            duration_ms=duration_ms,
            defect_triggered=defect_triggered,
            action_id=aid,
        )
        self.action_trail.append(rec.to_dict())
        return aid

    async def emit(self, kind: str, name: str, payload: dict[str, Any] | None = None) -> None:
        """Notify pipeline observers (e.g. API job event stream). Best-effort; never raises."""
        if self._pipeline_emit is None:
            return
        try:
            await self._pipeline_emit(kind, name, payload)
        except Exception as e:
            logger.debug("Pipeline emit failed (ignored): %s", e)

    async def _persist_scan(
        self,
        structured: dict,
        site_model: SiteModel | None,
        run_result: RunResult | None,
    ) -> None:
        """Best-effort PostgreSQL persistence; no-op if DATABASE_URL is unset."""
        structured.setdefault("report_id", str(uuid.uuid4()))
        try:
            from backend.db.persistence import persist_pipeline_result

            _scan_id, delta_report, report_id = await persist_pipeline_result(
                self.config.target_url,
                structured,
                site_model,
                run_result,
            )
            if report_id:
                structured["report_id"] = report_id
            if delta_report is not None:
                structured["delta_report"] = delta_report
        except Exception as e:
            logger.debug("Scan DB persistence skipped: %s", e)

    @staticmethod
    def _humanize_task_token(s: str) -> str:
        t = (s or "").strip()
        if not t:
            return "Scan"
        return " ".join(w.capitalize() for w in t.replace("-", "_").split("_") if w)

    def _execution_task_label(self) -> str:
        """Human-readable name for metrics: single micro-task, flow bundle, or preset group."""
        cfg = self.config
        tt = str(getattr(cfg, "task_type", "") or "").strip().lower()
        mt = str(getattr(cfg, "micro_task", "") or "").strip()
        if tt == "micro" and mt:
            return self._humanize_task_token(mt)
        flows = getattr(cfg, "flows", None)
        if isinstance(flows, list) and len(flows) > 0:
            parts = [self._humanize_task_token(str(x)) for x in flows if str(x).strip()]
            if len(parts) == 1:
                return parts[0]
            if len(parts) <= 4:
                return ", ".join(parts)
            return f"{len(parts)} micro-tasks ({', '.join(parts[:2])}, …)"
        st = str(getattr(cfg, "scan_task", "") or "").strip() or "full_app_scan"
        preset: dict[str, str] = {
            "quick_scan": "Quick scan",
            "conversion_scan": "Conversion scan",
            "full_app_scan": "Full app scan",
            "auth_scan": "Authentication scan",
        }
        return preset.get(st, self._humanize_task_token(st))

    def _pipeline_metrics(
        self,
        *,
        total_scan_time: float,
        crawl_time: float | None,
        execution_time: float | None,
        run_result: RunResult | None,
        pages_scanned: int | None,
    ) -> dict[str, Any]:
        retries = int(run_result.step_retries if run_result else 0)
        return {
            "total_scan_time": round(float(total_scan_time), 2),
            "crawl_time": round(float(crawl_time), 2) if crawl_time is not None else None,
            "execution_time": round(float(execution_time), 2)
            if execution_time is not None
            else None,
            "retries_count": retries,
            "step_retries": retries,
            "pages_scanned": int(pages_scanned) if pages_scanned is not None else None,
            "task": self._execution_task_label(),
        }

    @staticmethod
    def _log_pipeline_metrics(pm: dict[str, Any]) -> None:
        line = (
            f"PIPELINE_METRICS total_scan_time={pm['total_scan_time']}s "
            f"crawl_time={pm.get('crawl_time')}s "
            f"execution_time={pm.get('execution_time')}s "
            f"retries_count={pm.get('retries_count')} "
            f"pages_scanned={pm.get('pages_scanned')} "
            f"task={pm.get('task')!r}"
        )
        print(line, flush=True)
        logger.info("%s", line)

    def run_full_pipeline(self) -> dict:
        """Execute the pipeline and return structured JSON (always, even on failure)."""
        return asyncio.run(self._run_pipeline())

    async def _run_pipeline(self) -> dict:
        start = time.time()
        self._started_at = start
        self.action_trail = []
        self._session_id = self._action_job_id or f"pipeline_{uuid.uuid4().hex[:12]}"
        # ADD THIS — per-run screenshots under runs/<session_id>/screenshots/
        from backend.screenshot_manager import ScreenshotManager

        self._screenshot_mgr: ScreenshotManager | None = ScreenshotManager(self._session_id)
        # END ADD THIS
        site_model: SiteModel | None = None
        run_result: RunResult | None = None
        reports: dict[str, str] = {}
        registry_summary: dict = {}
        crawl_time_s: float | None = None
        execution_time_s: float | None = None
        pages_scanned: int | None = None

        logger.info("=== Starting deterministic pipeline (no AI) for %s ===", self.config.target_url)

        try:
            async with async_playwright() as playwright:
                browser = await launch_browser(
                    playwright,
                    browser_type=self.config.browser_type,
                    requires_login=bool(self.config.auth or self.config.requires_login),
                )
                browser_context = await create_stealth_context(
                    browser,
                    viewport={
                        "width": self.config.crawl.viewport.width,
                        "height": self.config.crawl.viewport.height,
                    },
                    user_agent=self.config.crawl.user_agent,
                )
                try:
                    auth_flow: AuthFlow | None = None
                    post_login_url: str | None = None
                    pipeline_auth_ok = True
                    if self.config.auth:
                        logger.info(
                            "--- Pipeline: authenticating shared browser context ---",
                        )
                        async def _emit_auth_message(msg: str) -> None:
                            await self.emit("action", "auth_message", {"message": msg})

                        ar = await perform_smart_auth(
                            browser_context,
                            self.config.auth,
                            ai_client=None,
                            emit_event=_emit_auth_message,
                        )
                        pipeline_auth_ok = ar.success
                        if ar.success:
                            auth_flow = ar.auth_flow
                            post_login_url = ar.post_login_url
                            logger.info("Pipeline authentication succeeded")
                        else:
                            logger.warning(
                                "Pipeline authentication failed: %s; continuing crawl "
                                "with unauthenticated context",
                                ar.error,
                            )

                    page = await browser_context.new_page()
                    credentials = dict(self.config.credentials or {})
                    if self.config.auth is not None:
                        credentials.setdefault("username", self.config.auth.username)
                        credentials.setdefault("password", self.config.auth.password)
                    if not credentials.get("username") and credentials.get("email"):
                        credentials["username"] = credentials["email"]
                    credentials["login_url"] = credentials.get("login_url") or self._login_nav_url()

                    async def emit_event(msg: str) -> None:
                        await self.emit("execution", "pipeline_message", {"message": msg})

                    login_success = False
                    try:
                        await emit_event("🔐 Handling authentication...")
                        login_success = await handle_login(page, credentials, emit_event)

                        if not login_success and credentials.get("username"):
                            await emit_event("⚠️ Running without login")

                        await emit_event("━━━ PHASE 1: CRAWLING ━━━")
                    finally:
                        await page.close()

                    pipeline_auth_ok = pipeline_auth_ok and login_success

                    # Stage 1: Optional crawl (discovery). Default off — execution is micro-task only.
                    if self.config.crawl_before_execution:
                        logger.info("--- Stage 1: Crawl ---")
                        await self.emit(
                            "stage",
                            "phase_1_crawling",
                            {"banner": PHASE_1_CRAWLING},
                        )
                        t_crawl0 = time.time()
                        site_model = await self._crawl(
                            browser=browser,
                            browser_context=browser_context,
                            post_login_url=post_login_url,
                            auth_flow=auth_flow,
                            log_action=self.log_action,
                            log_bracketed=self.log_action_bracketed,
                        )
                        crawl_time_s = round(time.time() - t_crawl0, 2)
                        pages_scanned = len(site_model.pages)
                        self._last_site_model = site_model
                        self._save_site_model(site_model)
                        self.crawled_pages = [p.url for p in (site_model.pages or []) if getattr(p, "url", None)]
                        if len(self.crawled_pages) <= 1:
                            nav_defect = {
                                "title": "Limited page discovery — only homepage crawled",
                                "description": (
                                    f"Crawler found only 1 page on {self.config.target_url}. "
                                    f"Navigation links may be JavaScript-rendered "
                                    f"or behind authentication."
                                ),
                                "element": "nav, header a, [role='navigation']",
                                "user_view": "Automated testing coverage is limited to the homepage only.",
                                "how_to_fix": (
                                    "Ensure navigation links are in the HTML source, "
                                    "not rendered by JavaScript after page load. "
                                    "Or enable login to access authenticated pages."
                                ),
                                "severity": "medium",
                                "business_impact": "ux",
                                "page_url": self.config.target_url,
                                "status": "open",
                            }
                            if not hasattr(self, "defects") or not isinstance(getattr(self, "defects"), list):
                                self.defects = []
                            self.defects.append(nav_defect)
                        logger.info(
                            "--- Stage 1 complete: %d pages in %.1fs ---",
                            len(site_model.pages),
                            crawl_time_s,
                        )
                        await self.emit(
                            "stage",
                            "crawl_complete",
                            {"pages": pages_scanned, "duration_s": crawl_time_s},
                        )
                    else:
                        logger.info(
                            "--- Skipping crawl: micro-task execution (task → action → result) ---",
                        )
                        site_model = _minimal_site_model_for_target(self.config.target_url)
                        crawl_time_s = 0.0
                        pages_scanned = len(site_model.pages)
                        self._last_site_model = site_model
                        self._save_site_model(site_model)
                        await self.emit(
                            "stage",
                            "phase_1_crawling",
                            {
                                "banner": PHASE_1_CRAWLING,
                                "skipped": True,
                                "mode": "micro_task_execution",
                            },
                        )
                        await self.emit(
                            "stage",
                            "crawl_complete",
                            {
                                "pages": pages_scanned,
                                "duration_s": 0.0,
                                "skipped": True,
                                "mode": "minimal_site_model",
                            },
                        )

                    await self.emit(
                        "stage",
                        "phase_2_execution",
                        {"banner": PHASE_2_EXECUTION},
                    )

                    # Stage 2: Deterministic plan
                    logger.info("--- Stage 2: Deterministic plan ---")
                    t_plan0 = time.time()
                    plan = self._deterministic_plan(site_model)
                    self._save_plan(plan)
                    logger.info(
                        "--- Stage 2 complete: %d test cases in %.1fs ---",
                        len(plan.test_cases),
                        time.time() - t_plan0,
                    )

                    # Stage 3: Execute (tool-based executor)
                    logger.info("--- Stage 3: Execute ---")
                    await self.emit("stage", "execution_start", {"tests": len(site_model.pages)})
                    t_exec0 = time.time()
                    run_result = await self._execute(
                        site_model,
                        plan,
                        browser=browser,
                        browser_context=browser_context,
                        pipeline_auth_satisfied=pipeline_auth_ok,
                        log_action=self.log_action,
                        log_bracketed=self.log_action_bracketed,
                    )
                    execution_time_s = round(time.time() - t_exec0, 2)
                    self._last_run_result = run_result
                    self._save_run_result(run_result)
                    logger.info(
                        "--- Stage 3 complete: %d passed, %d failed in %.1fs ---",
                        run_result.passed,
                        run_result.failed,
                        execution_time_s,
                    )
                    await self.emit(
                        "stage",
                        "execution_complete",
                        {
                            "passed": run_result.passed,
                            "failed": run_result.failed,
                            "duration_s": execution_time_s,
                        },
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

                    # HTML reports run after structured output + AI (see success path below).
                finally:
                    await browser.close()

        except Exception as e:
            logger.exception("Pipeline failed: %s", e)
            duration = round(time.time() - start, 2)
            print(f"PIPELINE total duration: {duration}s", flush=True)
            logger.info("PIPELINE total duration: %.2fs", duration)
            pm = self._pipeline_metrics(
                total_scan_time=duration,
                crawl_time=crawl_time_s,
                execution_time=execution_time_s,
                run_result=run_result,
                pages_scanned=pages_scanned,
            )
            self._log_pipeline_metrics(pm)
            out = await build_structured_output(
                site_model=site_model,
                run_result=run_result,
                pipeline_error=str(e),
                extra={
                    "run_id": run_result.run_id if run_result else None,
                    "duration": duration,
                    "mode": "deterministic_no_ai",
                    "scan_mode": self.config.scan_mode,
                    "scan_task": self.config.scan_task,
                    "target_url": self.config.target_url,
                    "results": None,
                    "execution_snapshot": run_result.execution_snapshot if run_result else None,
                    "coverage": registry_summary,
                    "reports": reports,
                    "pipeline_metrics": pm,
                    "action_trail": list(self.action_trail),
                    "actions": list(self.action_trail),
                    "actions_run": len(list(self.action_trail)),
                    "defects": list(getattr(self, "defects", []) or []),
                    "issues": list(getattr(self, "defects", []) or []),
                    **site_pages_payload(site_model),
                },
            )
            await self._persist_scan(out, site_model, run_result)
            await self.emit(
                "stage",
                "phase_3_ai_analysis",
                {"banner": PHASE_3_AI_ANALYSIS},
            )
            await attach_risk_explanation(out)
            await self.log_action(
                None,
                phase="analyze",
                action_type="evaluate",
                description="attach_risk_explanation",
                outcome="success",
            )
            await attach_decision_insights(out)
            await self.log_action(
                None,
                phase="analyze",
                action_type="evaluate",
                description="attach_decision_insights",
                outcome="success",
            )
            await self.emit(
                "stage",
                "phase_4_report",
                {"banner": PHASE_4_REPORT},
            )
            try:
                logger.info("--- Stage 5: Report ---")
                if run_result:
                    previous_run = self._load_previous_run_result(run_result.run_id)
                    registry = self.registry_manager.load()
                    reports = self._report(run_result, registry, previous_run=previous_run)
                else:
                    reports = {}
            except Exception as e:
                logger.warning("Report generation skipped: %s", e)
                reports = {}
            out["reports"] = reports
            return out

        duration = round(time.time() - start, 2)
        print(f"PIPELINE total duration: {duration}s", flush=True)
        logger.info("PIPELINE total duration: %.2fs", duration)
        pm = self._pipeline_metrics(
            total_scan_time=duration,
            crawl_time=crawl_time_s,
            execution_time=execution_time_s,
            run_result=run_result,
            pages_scanned=pages_scanned,
        )
        self._log_pipeline_metrics(pm)
        extra = {
            "run_id": run_result.run_id if run_result else None,
            "duration": duration,
            "mode": "deterministic_no_ai",
            "scan_mode": self.config.scan_mode,
            "scan_task": self.config.scan_task,
            "target_url": self.config.target_url,
            "results": {
                "total": run_result.total_tests,
                "passed": run_result.passed,
                "failed": run_result.failed,
                "skipped": run_result.skipped,
                "errors": run_result.errors,
            }
            if run_result
            else None,
            "execution_snapshot": run_result.execution_snapshot if run_result else None,
            "coverage": registry_summary,
            "reports": reports,
            "pipeline_metrics": pm,
            "action_trail": list(self.action_trail),
            "actions": list(self.action_trail),
            "actions_run": len(list(self.action_trail)),
            "defects": list(getattr(self, "defects", []) or []),
            "issues": list(getattr(self, "defects", []) or []),
            **site_pages_payload(site_model),
        }
        out = await build_structured_output(
            site_model=site_model,
            run_result=run_result,
            pipeline_error=None,
            extra=extra,
        )
        await self._persist_scan(out, site_model, run_result)
        await self.emit(
            "stage",
            "phase_3_ai_analysis",
            {"banner": PHASE_3_AI_ANALYSIS},
        )
        await attach_risk_explanation(out)
        await self.log_action(
            None,
            phase="analyze",
            action_type="evaluate",
            description="attach_risk_explanation",
            outcome="success",
        )
        await attach_decision_insights(out)
        await self.log_action(
            None,
            phase="analyze",
            action_type="evaluate",
            description="attach_decision_insights",
            outcome="success",
        )
        await self.emit(
            "stage",
            "phase_4_report",
            {"banner": PHASE_4_REPORT},
        )
        try:
            logger.info("--- Stage 5: Report ---")
            if run_result:
                previous_run = self._load_previous_run_result(run_result.run_id)
                registry = self.registry_manager.load()
                reports = self._report(run_result, registry, previous_run=previous_run)
            else:
                reports = {}
        except Exception as e:
            logger.warning("Report generation skipped: %s", e)
            reports = {}
        out["reports"] = reports
        return out

    async def build_partial_result(self, warning_message: str) -> dict[str, object]:
        duration = round(time.time() - self._started_at, 2)
        sm = self._last_site_model
        pages = len(sm.pages) if sm else None
        pm = self._pipeline_metrics(
            total_scan_time=duration,
            crawl_time=None,
            execution_time=None,
            run_result=self._last_run_result,
            pages_scanned=pages,
        )
        self._log_pipeline_metrics(pm)
        out = await build_structured_output(
            site_model=self._last_site_model,
            run_result=self._last_run_result,
            pipeline_error=None,
            extra={
                "run_id": self._last_run_result.run_id if self._last_run_result else None,
                "duration": duration,
                "mode": "deterministic_no_ai",
                "scan_mode": self.config.scan_mode,
                "scan_task": self.config.scan_task,
                "target_url": self.config.target_url,
                "status": "partial",
                "warning": warning_message,
                "execution_snapshot": self._last_run_result.execution_snapshot
                if self._last_run_result
                else None,
                "pipeline_metrics": pm,
                "action_trail": list(self.action_trail),
                "actions": list(self.action_trail),
                "actions_run": len(list(self.action_trail)),
                "defects": list(getattr(self, "defects", []) or []),
                "issues": list(getattr(self, "defects", []) or []),
                **site_pages_payload(self._last_site_model),
            },
        )
        # Caller attaches risk_explanation after persist + delta_report merge (see api/server.py timeout path).
        return out

    async def _crawl(
        self,
        *,
        browser: Browser | None = None,
        browser_context: BrowserContext | None = None,
        post_login_url: str | None = None,
        auth_flow: AuthFlow | None = None,
        log_action: Any | None = None,
        log_bracketed: Any | None = None,
    ) -> SiteModel:
        site_model_dir = self.framework_dir / "site_model"
        crawler = Crawler(self.config, site_model_dir, ai_client=None)
        emit = self.emit
        if browser is not None and browser_context is not None:
            return await crawler.crawl(
                browser_context=browser_context,
                browser=browser,
                skip_auth=True,
                post_login_url=post_login_url,
                auth_flow_override=auth_flow,
                emit=emit,
                log_action=log_action,
                log_bracketed=log_bracketed,
            )
        return await crawler.crawl(emit=emit, log_action=log_action, log_bracketed=log_bracketed)

    def run_crawl_only(self) -> SiteModel:
        return asyncio.run(self._crawl())

    def _deterministic_plan(self, site_model: SiteModel) -> TestPlan:
        return build_deterministic_smoke_plan(self.config, site_model)

    def run_plan_only(self) -> TestPlan:
        site_model = self._load_site_model()
        return self._deterministic_plan(site_model)

    async def _execute(
        self,
        site_model: SiteModel,
        plan: TestPlan,
        *,
        browser: Browser | None = None,
        browser_context: BrowserContext | None = None,
        pipeline_auth_satisfied: bool = True,
        log_action: Any | None = None,
        log_bracketed: Any | None = None,
    ) -> RunResult:
        """Run micro-task ecommerce scan once (``run_ecommerce_scan``); no crawl dependency."""
        _ = pipeline_auth_satisfied  # pipeline auth already applied to shared context
        _ = site_model  # optional crawl snapshot for reporting only; execution uses page + config only
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        t0 = time.time()
        run_id = f"run_{uuid.uuid4().hex[:8]}"

        async def run_on_context(bc: BrowserContext) -> RunResult:
            page = await bc.new_page()
            test_results: list[TestResult] = []
            execution_logs: list[str] = []
            goto_timeout = min(
                120_000,
                max(15_000, int(self.config.selector_timeout_seconds * 1000)),
            )
            try:
                credentials: dict[str, Any] = dict(self.config.credentials or {})
                credentials.setdefault("target_url", self.config.target_url)
                credentials.setdefault("browse_start_url", self.config.target_url)
                if self.config.auth is not None:
                    credentials.setdefault("email", self.config.auth.username)
                    credentials.setdefault("username", self.config.auth.username)
                    credentials.setdefault("password", self.config.auth.password)

                task_type = str(getattr(self.config, "task_type", "") or "").strip().lower()
                micro_task = str(getattr(self.config, "micro_task", "") or "").strip()

                async def emit_event(msg: str) -> None:
                    execution_logs.append(str(msg))
                    await self.emit("execution", "qa_action", {"message": msg})

                # Single source of truth for micro tasks: shared context (not credentials).
                context = create_context()
                context.update(credentials or {})

                ti = str(getattr(self.config, "task_input", "") or "").strip()
                sq = extract_search_query_from_task_input(ti) if ti else None
                if sq:
                    context["search_query"] = sq
                    await emit_event(f"Using user intent: {sq}")

                try:
                    if log_bracketed:

                        async def _goto_target() -> None:
                            await page.goto(
                                self.config.target_url,
                                wait_until="domcontentloaded",
                                timeout=goto_timeout,
                            )

                        await log_bracketed(
                            page,
                            phase="execute",
                            action_type="navigate",
                            description="Navigate to target for ecommerce scan",
                            target_url=self.config.target_url,
                            coro=_goto_target,
                        )
                    else:
                        await page.goto(
                            self.config.target_url,
                            wait_until="domcontentloaded",
                            timeout=goto_timeout,
                        )
                    # ADD THIS — full-page shot after successful entry URL load
                    _sm = getattr(self, "_screenshot_mgr", None)
                    if _sm is not None:
                        await _sm.capture_page(
                            page, "after_initial_goto", page.url or ""
                        )
                    # END ADD THIS
                except Exception as e:
                    logger.warning("Ecommerce scan initial navigation failed: %s", e)
                    try:
                        from backend.core.defects import make_defect

                        nav_defect = make_defect(
                            defect="page_load_failure",
                            title=f"Initial navigation failed on {self.config.target_url}",
                            description=f"page.goto({self.config.target_url!r}) raised: {type(e).__name__}: {str(e)}",
                            element="page.goto",
                            page_url=self.config.target_url,
                            severity="critical",
                            business_impact="revenue",
                            user_view="User cannot load the site to start the journey; scan could not proceed.",
                            how_to_fix="Fix the initial page load/navigation failure (DNS/TLS, redirects, bot protection, or timeout). Then re-run the scan.",
                            extra={"evidence": str(e)[:500]},
                        )
                    except Exception:
                        nav_defect = {
                            "defect": "page_load_failure",
                            "severity": "critical",
                            "page_url": self.config.target_url,
                            "description": f"Initial navigation failed: {type(e).__name__}: {str(e)}",
                            "title": "DEFECT_TITLE_MISSING — fix in backend/orchestrator.py",
                        }
                    if log_action:
                        await log_action(
                            page,
                            phase="execute",
                            action_type="navigate",
                            description=f"Ecommerce scan navigation failed: {self.config.target_url[:200]}",
                            target_url=self.config.target_url,
                            outcome="failed",
                            outcome_detail=str(e)[:500],
                        )
                    pid = page_id_from_url(self.config.target_url)
                    test_results.append(
                        TestResult(
                            test_id="ecommerce_scan",
                            test_name="E-commerce scan",
                            description="Ecommerce scan failed during initial navigation",
                            category="functional",
                            priority=1,
                            target_page_id=pid,
                            actual_page_id=pid,
                            actual_url=page.url,
                            coverage_signature="ecommerce_scan_v1",
                            result="error",
                            duration_seconds=round(time.time() - t0, 2),
                            failure_reason=str(e),
                            qa_defects_by_page=[
                                {
                                    "page_url": self.config.target_url,
                                    "defects": [nav_defect],
                                    "metrics": {"stage": "initial_goto"},
                                }
                            ],
                        )
                    )
                    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                    return RunResult(
                        run_id=run_id,
                        plan_id=plan.plan_id,
                        started_at=started_at,
                        completed_at=completed_at,
                        target_url=plan.target_url,
                        total_tests=len(test_results),
                        passed=0,
                        failed=0,
                        skipped=0,
                        errors=len(test_results),
                        duration_seconds=round(time.time() - t0, 2),
                        test_results=test_results,
                        step_retries=0,
                        execution_snapshot=_build_execution_snapshot(
                            page_url=str(page.url or self.config.target_url),
                            defects=[nav_defect],
                            results={},
                            task_type="",
                            logs=execution_logs,
                            duration_seconds=round(time.time() - t0, 2),
                        ),
                    )

                t_scan = time.time()
                if task_type == "micro":
                    if not micro_task:
                        pid = page_id_from_url(page.url)
                        test_results.append(
                            TestResult(
                                test_id="micro_task",
                                test_name="Micro task",
                                description="micro_task is required when task_type=micro",
                                category="functional",
                                priority=1,
                                target_page_id=pid,
                                actual_page_id=pid,
                                actual_url=page.url,
                                coverage_signature="micro_task_v1",
                                result="error",
                                duration_seconds=round(time.time() - t_scan, 2),
                                failure_reason="micro_task missing",
                                qa_defects_by_page=[],
                            )
                        )
                        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        return RunResult(
                            run_id=run_id,
                            plan_id=plan.plan_id,
                            started_at=started_at,
                            completed_at=completed_at,
                            target_url=plan.target_url,
                            total_tests=len(test_results),
                            passed=0,
                            failed=0,
                            skipped=0,
                            errors=len(test_results),
                            duration_seconds=round(time.time() - t0, 2),
                            test_results=test_results,
                            step_retries=0,
                            execution_snapshot=_build_execution_snapshot(
                                page_url=str(page.url or self.config.target_url),
                                defects=[],
                                results={},
                                task_type="micro",
                                logs=execution_logs,
                                duration_seconds=round(time.time() - t_scan, 2),
                            ),
                        )
                    results = await run_micro_task(page, micro_task, context, emit_event)
                else:
                    raw_flows = getattr(self.config, "flows", None)
                    if isinstance(raw_flows, list) and len(raw_flows) > 0:
                        selected_flows = expand_selected_flows([str(x) for x in raw_flows if x])
                    else:
                        st = str(self.config.scan_task or "full_app_scan").strip() or "full_app_scan"
                        selected_flows = expand_selected_flows([st])
                    print(f"[SCAN EXEC] calling run_ecommerce_scan now", flush=True)
                    results = await run_ecommerce_scan(page, selected_flows, context, emit_event)

                    # Wire action trail from ecommerce flows into orchestrator
                    if isinstance(results, dict):
                        flow_actions = results.get("actions", [])
                        if hasattr(self, "action_trail"):
                            if isinstance(flow_actions, list):
                                self.action_trail.extend(flow_actions)
                        else:
                            self.action_trail = flow_actions if isinstance(flow_actions, list) else []

                        flow_defects = results.get("defects", [])
                        if hasattr(self, "defects"):
                            if isinstance(flow_defects, list):
                                self.defects.extend(flow_defects)
                        else:
                            self.defects = flow_defects if isinstance(flow_defects, list) else []

                # ADD THIS — post-scan page + per-defect evidence + final state
                _sm = getattr(self, "_screenshot_mgr", None)
                if _sm is not None:
                    await _sm.capture_page(page, "after_flow_scan", page.url or "")
                # END ADD THIS
                defects = results.get("defects") or []
                # ADD THIS
                if _sm is not None:
                    for _d in defects:
                        if isinstance(_d, dict):
                            _sel = (
                                str(
                                    _d.get("selector")
                                    or _d.get("element")
                                    or "body"
                                ).strip()
                                or "body"
                            )
                            _lab = str(
                                _d.get("defect")
                                or _d.get("defect_id")
                                or _d.get("type")
                                or "issue"
                            )
                            _meta = await _sm.capture_element(
                                page, _sel, _lab, page.url or ""
                            )
                            if _meta:
                                _up = str(_meta.get("url_path") or "")
                                _d["screenshot_path"] = _up
                                _d["evidence"] = _up
                    await _sm.capture_page(page, "final_state", page.url or "")
                # END ADD THIS
                pid = page_id_from_url(page.url)
                test_name = (
                    f"Micro task: {micro_task}"
                    if task_type == "micro" and micro_task
                    else "Micro task scan"
                )
                test_id = "micro_task" if task_type == "micro" else "micro_task_scan"
                coverage_sig = "micro_task_v1" if task_type == "micro" else "micro_task_scan_v1"
                test_results.append(
                    TestResult(
                        test_id=test_id,
                        test_name=test_name,
                        description="Single micro-task run"
                        if task_type == "micro"
                        else f"Micro task orchestration ({len(TASK_REGISTRY)} tasks in registry)",
                        category="functional",
                        priority=1,
                        target_page_id=pid,
                        actual_page_id=pid,
                        actual_url=page.url,
                        coverage_signature=coverage_sig,
                        result="fail" if defects else "pass",
                        duration_seconds=round(time.time() - t_scan, 2),
                        qa_defects_by_page=[
                            {
                                "page_url": page.url,
                                "defects": defects,
                                "metrics": results.get("metrics"),
                            },
                        ],
                    )
                )

                n_issues = len(defects)
                await emit_event(f"Execution complete — {n_issues} issues detected")

                completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                passed = sum(1 for tr in test_results if tr.result == "pass")
                failed = sum(1 for tr in test_results if tr.result == "fail")
                errors = sum(1 for tr in test_results if tr.result == "error")
                execution_snapshot = _build_execution_snapshot(
                    page_url=str(page.url or self.config.target_url),
                    defects=defects,
                    results=results,
                    task_type=task_type,
                    logs=execution_logs,
                    duration_seconds=round(time.time() - t_scan, 2),
                )
                return RunResult(
                    run_id=run_id,
                    plan_id=plan.plan_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    target_url=plan.target_url,
                    total_tests=len(test_results),
                    passed=passed,
                    failed=failed,
                    skipped=0,
                    errors=errors,
                    duration_seconds=round(time.time() - t0, 2),
                    test_results=test_results,
                    step_retries=0,
                    execution_snapshot=execution_snapshot,
                )
            finally:
                await page.close()

        if browser is not None and browser_context is not None:
            return await run_on_context(browser_context)

        async with async_playwright() as playwright:
            browser_launched = await launch_browser(
                playwright,
                browser_type=self.config.browser_type,
                requires_login=bool(self.config.auth or self.config.requires_login),
            )
            bc = await create_stealth_context(
                browser_launched,
                viewport={
                    "width": self.config.crawl.viewport.width,
                    "height": self.config.crawl.viewport.height,
                },
                user_agent=self.config.crawl.user_agent,
            )
            try:
                return await run_on_context(bc)
            finally:
                await browser_launched.close()

    def run_execute_only(self, plan: TestPlan) -> RunResult:
        site_model = self._load_site_model()
        return asyncio.run(self._execute(site_model, plan))

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
