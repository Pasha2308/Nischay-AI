"""Test executor — runs test plans using Playwright."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.browser import launch_browser
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from shared.utils.ai.client import AIClient
from shared.utils.auth import authenticate_and_capture_state
from shared.utils.browser_stealth import create_stealth_context
from shared.utils.coverage.visual_baseline_registry import VisualBaselineRegistryManager
from shared.pipeline_emit import PipelineEmit
from shared.models.config import FrameworkConfig
from shared.models.test_plan import Action, TestCase, TestPlan
from shared.models.test_result import (
    AssertionResult as AssertionResultModel,
    RunResult,
    StepResult,
    TestResult,
)
from shared.models.visual_baseline import VisualBaselineRegistry
from shared.utils.auth import perform_smart_auth
from shared.utils.url_utils import page_id_from_url

from backend.agents.evaluator_agent import EvaluatorAgent
from backend.core.action_engine import collect_console_defects_light

from .action_runner import resolve_dynamic_vars_for_test_case, run_action
from .assertion_checker import check_assertion
from .evidence_collector import EvidenceCollector
from .fallback import FallbackHandler
from .tools.registry import TOOL_REGISTRY, tool_names_for_plan, tool_names_for_test_case

logger = logging.getLogger(__name__)

LOW_VALUE_ASSERTION_TYPES = frozenset({"screenshot_diff", "ai_evaluate", "element_count"})


def _action_summary_for_eval(action: Action) -> str:
    parts = [action.action_type]
    if action.selector:
        parts.append(f"selector={action.selector!r}")
    if action.value:
        parts.append(f"value={action.value!r}")
    return " · ".join(parts)


class Executor:
    """Executes test plans against a live site using Playwright."""

    def __init__(
        self,
        config: FrameworkConfig,
        ai_client: AIClient | None,
        runs_dir: Path,
        visual_registry: VisualBaselineRegistry | None = None,
        visual_registry_manager: VisualBaselineRegistryManager | None = None,
    ):
        self.config = config
        self.ai_client = ai_client
        self.runs_dir = runs_dir
        self.run_id = f"run_{uuid.uuid4().hex[:8]}"
        self.run_dir = runs_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.visual_registry = visual_registry
        self.visual_registry_manager = visual_registry_manager
        self.step_retries = 0
        self._step_retry_lock = asyncio.Lock()

    async def _record_step_retry(self) -> None:
        async with self._step_retry_lock:
            self.step_retries += 1

    async def _execute_shared_browser(
        self,
        plan: TestPlan,
        baseline_dir: Path | None,
        browser: Browser,
        browser_context: BrowserContext,
        pipeline_auth_satisfied: bool,
        emit: PipelineEmit | None = None,
    ) -> RunResult:
        """Run tests on the pipeline's single shared context (session + cookies preserved)."""
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time = time.time()
        self.step_retries = 0
        total_tests = len(plan.test_cases)
        logger.info(
            "Starting execution (shared browser context) for plan %s (%d tests)",
            plan.plan_id,
            total_tests,
        )

        sorted_tests = sorted(plan.test_cases, key=lambda tc: tc.priority)
        auth_failure_result: TestResult | None = None
        auth_success_result: TestResult | None = None

        if self.config.auth:
            if not pipeline_auth_satisfied:
                logger.error("Pipeline auth did not succeed; skipping tests")
                auth_failure_result = TestResult(
                    test_id="auth_login",
                    test_name="Authentication login",
                    description="Login attempt before running tests",
                    category="functional",
                    priority=1,
                    target_page_id="",
                    coverage_signature="auth_login",
                    result="error",
                    duration_seconds=0.0,
                    failure_reason="AUTH_LOGIN_FAILED: pipeline authentication failed",
                )
                test_results = [auth_failure_result]
                duration = time.time() - start_time
                completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                return RunResult(
                    run_id=self.run_id,
                    plan_id=plan.plan_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    target_url=plan.target_url,
                    total_tests=len(test_results),
                    passed=0,
                    failed=0,
                    skipped=0,
                    errors=1,
                    duration_seconds=round(duration, 2),
                    test_results=test_results,
                    step_retries=self.step_retries,
                )
            auth_success_result = TestResult(
                test_id="auth_login",
                test_name="Authentication login",
                description="Session from shared pipeline context",
                category="functional",
                priority=1,
                target_page_id="",
                coverage_signature="auth_login",
                result="pass",
                duration_seconds=0.0,
            )

        try:
            # One test at a time — shared context avoids parallel tab races
            semaphore = asyncio.Semaphore(1)
            auth_lock = asyncio.Lock()

            async def _run_one_shared(index: int, tc: TestCase) -> TestResult:
                async with semaphore:
                    elapsed = time.time() - start_time
                    if elapsed >= self.config.max_execution_time_seconds:
                        return TestResult(
                            test_id=tc.test_id,
                            test_name=tc.name,
                            description=tc.description,
                            category=tc.category,
                            priority=tc.priority,
                            target_page_id=tc.target_page_id,
                            coverage_signature=tc.coverage_signature,
                            result="skip",
                            failure_reason="Time limit reached",
                        )

                    logger.info(
                        "Running test [%d/%d] (shared context): %s",
                        index + 1,
                        total_tests,
                        tc.name,
                    )
                    result = await self._run_test(
                        browser_context, tc, baseline_dir, emit=emit,
                    )
                    logger.info(
                        "[%s] %s: %s (%.1fs)",
                        result.result.upper(),
                        tc.test_id,
                        tc.name,
                        result.duration_seconds or 0,
                    )

                    if self.config.auth and self._session_invalidated(result):
                        async with auth_lock:
                            logger.info(
                                "Session invalidated by %s, re-authenticating in shared context...",
                                tc.test_id,
                            )
                            r = await perform_smart_auth(
                                browser_context,
                                self.config.auth,
                                ai_client=self.ai_client,
                            )
                            if not r.success:
                                logger.error("Re-auth failed: %s", r.error)

                    return result

            thr = int(getattr(self.config, "executor_early_exit_critical_threshold", 0) or 0)
            critical_accum = 0
            early_stopped = False
            test_results: list[TestResult] = []
            for i, tc in enumerate(sorted_tests):
                if early_stopped:
                    test_results.append(
                        TestResult(
                            test_id=tc.test_id,
                            test_name=tc.name,
                            description=tc.description,
                            category=tc.category,
                            priority=tc.priority,
                            target_page_id=tc.target_page_id,
                            coverage_signature=tc.coverage_signature,
                            result="skip",
                            failure_reason="Early exit: critical failure threshold reached",
                        )
                    )
                    continue
                result = await _run_one_shared(i, tc)
                test_results.append(result)
                if thr > 0 and self._counts_as_critical_failure(result, tc):
                    critical_accum += 1
                    if critical_accum >= thr:
                        logger.info(
                            "Early exit: %d critical failure(s) (threshold=%d); remaining tests skipped",
                            critical_accum,
                            thr,
                        )
                        early_stopped = True
            if self.config.auth:
                if auth_failure_result:
                    test_results.insert(0, auth_failure_result)
                elif auth_success_result:
                    test_results.insert(0, auth_success_result)
            logger.info("Collecting results (shared context)")
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.error("Executor Playwright failure (shared context): %s", e)
            test_results = [
                TestResult(
                    test_id="playwright_runtime",
                    test_name="Playwright runtime",
                    description="Playwright runtime failure",
                    category="functional",
                    priority=1,
                    target_page_id="",
                    coverage_signature="playwright_runtime",
                    result="error",
                    duration_seconds=0.0,
                    failure_reason=str(e),
                )
            ]
        except Exception as e:
            logger.error("Executor failed (shared context): %s", e)
            test_results = [
                TestResult(
                    test_id="executor_bootstrap",
                    test_name="Executor bootstrap",
                    description="Playwright/browser error",
                    category="functional",
                    priority=1,
                    target_page_id="",
                    coverage_signature="executor_bootstrap",
                    result="error",
                    duration_seconds=0.0,
                    failure_reason=str(e),
                )
            ]

        duration = time.time() - start_time
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        run_result = RunResult(
            run_id=self.run_id,
            plan_id=plan.plan_id,
            started_at=started_at,
            completed_at=completed_at,
            target_url=plan.target_url,
            total_tests=len(test_results),
            passed=sum(1 for r in test_results if r.result == "pass"),
            failed=sum(1 for r in test_results if r.result == "fail"),
            skipped=sum(1 for r in test_results if r.result == "skip"),
            errors=sum(1 for r in test_results if r.result == "error"),
            duration_seconds=round(duration, 2),
            test_results=test_results,
            step_retries=self.step_retries,
        )
        logger.info(
            "Execution complete (shared): %d passed, %d failed, %d skipped, %d errors (%.1fs)",
            run_result.passed,
            run_result.failed,
            run_result.skipped,
            run_result.errors,
            duration,
        )
        return run_result

    async def execute(
        self,
        plan: TestPlan,
        baseline_dir: Path | None = None,
        *,
        browser: Browser | None = None,
        browser_context: BrowserContext | None = None,
        pipeline_auth_satisfied: bool = True,
        emit: PipelineEmit | None = None,
    ) -> RunResult:
        """Execute a full test plan and return results.

        Each test runs in a fully isolated browser context. If auth is
        configured, the session state (cookies + localStorage) is captured
        once and injected into each test's context via Playwright's
        storageState API — no repeated logins.

        When ``browser`` and ``browser_context`` are passed (pipeline mode), tests run
        sequentially on that shared context so crawl + execute share cookies/session.
        """
        if browser is not None and browser_context is not None:
            return await self._execute_shared_browser(
                plan,
                baseline_dir,
                browser,
                browser_context,
                pipeline_auth_satisfied,
                emit=emit,
            )

        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time = time.time()
        self.step_retries = 0
        total_tests = len(plan.test_cases)
        logger.info("Starting execution of plan %s (%d tests)",
                     plan.plan_id, total_tests)

        plan_action_types = tool_names_for_plan(plan)
        logger.info(
            "Plan %s action types (tool dispatch): %s",
            plan.plan_id,
            sorted(plan_action_types),
        )
        unregistered_plan = sorted(a for a in plan_action_types if a not in TOOL_REGISTRY)
        if unregistered_plan:
            logger.warning(
                "Plan %s includes unregistered action types (steps will error): %s",
                plan.plan_id,
                unregistered_plan,
            )

        sorted_tests = sorted(plan.test_cases, key=lambda tc: tc.priority)
        test_results: list[TestResult] = []
        auth_failure_result: TestResult | None = None
        auth_success_result: TestResult | None = None

        try:
            async with async_playwright() as playwright:
                logger.info("Launching browser (type=%s)", self.config.browser_type)
                logger.debug("Launching Playwright for test execution...")
                browser = await launch_browser(
                    playwright,
                    browser_type=self.config.browser_type,
                    requires_login=bool(self.config.auth),
                )

                # Capture auth state once — will be injected into per-test contexts
                auth_storage_state: dict | None = None
                if self.config.auth:
                    logger.info("Authenticating to capture session state...")
                    auth_result, auth_storage_state = await authenticate_and_capture_state(
                        browser,
                        self.config.auth,
                        ai_client=self.ai_client,
                        viewport={"width": 1280, "height": 720},
                        user_agent=self.config.crawl.user_agent,
                    )
                    if auth_result.success:
                        method = auth_result.auth_flow.detection_method if auth_result.auth_flow else "unknown"
                        logger.info("Auth state captured successfully (method=%s)", method)
                        auth_success_result = TestResult(
                            test_id="auth_login",
                            test_name="Authentication login",
                            description="Login validated before running tests",
                            category="functional",
                            priority=1,
                            target_page_id="",
                            coverage_signature="auth_login",
                            result="pass",
                            duration_seconds=0.0,
                        )
                    else:
                        logger.error("Initial auth failed: %s", auth_result.error)
                        auth_failure_result = TestResult(
                            test_id="auth_login",
                            test_name="Authentication login",
                            description="Login attempt before running tests",
                            category="functional",
                            priority=1,
                            target_page_id="",
                            coverage_signature="auth_login",
                            result="error",
                            duration_seconds=0.0,
                            failure_reason=f"AUTH_LOGIN_FAILED: {auth_result.error or 'unknown error'}",
                        )
                        test_results = [auth_failure_result]
                        logger.info("Collecting results")
                        await browser.close()
                        duration = time.time() - start_time
                        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        return RunResult(
                            run_id=self.run_id,
                            plan_id=plan.plan_id,
                            started_at=started_at,
                            completed_at=completed_at,
                            target_url=plan.target_url,
                            total_tests=len(test_results),
                            passed=0,
                            failed=0,
                            skipped=0,
                            errors=1,
                            duration_seconds=round(duration, 2),
                            test_results=test_results,
                            step_retries=self.step_retries,
                        )

                # Run tests in parallel, bounded by max_parallel_contexts
                semaphore = asyncio.Semaphore(self.config.max_parallel_contexts)
                auth_lock = asyncio.Lock()
                auth_state: dict[str, dict | None] = {"storage": auth_storage_state}

                async def _run_one(index: int, tc: TestCase) -> TestResult:
                    async with semaphore:
                        elapsed = time.time() - start_time
                        if elapsed >= self.config.max_execution_time_seconds:
                            logger.warning("Time limit reached, skipping %s", tc.name)
                            return TestResult(
                                test_id=tc.test_id, test_name=tc.name,
                                description=tc.description, category=tc.category,
                                priority=tc.priority, target_page_id=tc.target_page_id,
                                coverage_signature=tc.coverage_signature,
                                result="skip", failure_reason="Time limit reached",
                            )

                        logger.info("Running test [%d/%d]: %s (%s)",
                                    index + 1, total_tests, tc.name, tc.category)
                        logger.debug("  Test ID: %s | Page: %s | Timeout: %ds | requires_auth: %s",
                                     tc.test_id, tc.target_page_id, tc.timeout_seconds,
                                     tc.requires_auth)

                        storage = auth_state["storage"] if (tc.requires_auth and self.config.auth) else None
                        capture_mode = self.config.capture_video

                        # For "always" mode, prepare video dir before context creation
                        video_dir: Path | None = None
                        record_video_dir_arg: str | None = None
                        if capture_mode == "always":
                            evidence_dir = self.run_dir / "evidence" / tc.test_id
                            evidence_dir.mkdir(parents=True, exist_ok=True)
                            video_dir = evidence_dir / "video"
                            video_dir.mkdir(parents=True, exist_ok=True)
                            record_video_dir_arg = str(video_dir)

                        context = await create_stealth_context(
                            browser,
                            viewport={"width": 1280, "height": 720},
                            user_agent=self.config.crawl.user_agent,
                            storage_state=storage,
                            record_video_dir=record_video_dir_arg,
                        )
                        try:
                            result = await self._run_test(context, tc, baseline_dir, emit=emit)
                            logger.info("[%s] %s: %s (%.1fs)",
                                        result.result.upper(), tc.test_id, tc.name,
                                        result.duration_seconds or 0)

                            if self.config.auth and self._session_invalidated(result):
                                async with auth_lock:
                                    logger.info("Session invalidated by %s, re-capturing auth state...",
                                                tc.test_id)
                                    auth_result, new_state = await authenticate_and_capture_state(
                                        browser,
                                        self.config.auth,
                                        ai_client=self.ai_client,
                                        viewport={"width": 1280, "height": 720},
                                        user_agent=self.config.crawl.user_agent,
                                    )
                                    if auth_result.success:
                                        auth_state["storage"] = new_state
                                    else:
                                        logger.error("Re-auth after session invalidation failed: %s",
                                                     auth_result.error)
                        finally:
                            await context.close()

                        # "always" mode: attach video after context close finalizes it
                        if capture_mode == "always" and video_dir:
                            video_path = self._find_video_file(video_dir)
                            if video_path:
                                result.evidence.video_path = video_path
                                logger.debug("Video recorded for %s: %s", tc.test_id, video_path)

                        # "on_failure" mode: re-run failed tests with video
                        if capture_mode == "on_failure" and result.result in ("fail", "error"):
                            elapsed = time.time() - start_time
                            if elapsed < self.config.max_execution_time_seconds:
                                logger.info("Re-running %s with video capture for failure analysis...",
                                            tc.test_id)
                                rerun_evidence_dir = self.run_dir / "evidence" / tc.test_id / "video_rerun"
                                rerun_evidence_dir.mkdir(parents=True, exist_ok=True)
                                rerun_video_dir = rerun_evidence_dir / "video"
                                rerun_video_dir.mkdir(parents=True, exist_ok=True)

                                video_context = await create_stealth_context(
                                    browser,
                                    viewport={"width": 1280, "height": 720},
                                    user_agent=self.config.crawl.user_agent,
                                    storage_state=storage,
                                    record_video_dir=str(rerun_video_dir),
                                )
                                try:
                                    video_result = await self._run_test(
                                        video_context, tc, baseline_dir, emit=emit,
                                    )
                                finally:
                                    await video_context.close()

                                video_path = self._find_video_file(rerun_video_dir)
                                if video_path:
                                    result.evidence.video_path = video_path
                                    logger.debug("Failure video for %s: %s", tc.test_id, video_path)

                                # Flaky detection: re-run passed but original failed
                                if video_result.result == "pass":
                                    result.potentially_flaky = True
                                    logger.warning(
                                        "Test %s is potentially flaky: failed initially but passed on re-run",
                                        tc.test_id,
                                    )
                            else:
                                logger.warning("Skipping video re-run for %s: time limit approaching",
                                               tc.test_id)

                        return result

                test_results = list(await asyncio.gather(
                    *(_run_one(i, tc) for i, tc in enumerate(sorted_tests))
                ))
                if self.config.auth:
                    if auth_failure_result:
                        test_results.insert(0, auth_failure_result)
                    elif auth_success_result:
                        test_results.insert(0, auth_success_result)
                logger.info("Collecting results")
                await browser.close()
        except (PlaywrightTimeoutError, PlaywrightError) as e:
            logger.error("Executor Playwright failure (launch/runtime): %s", e)
            test_results = [
                TestResult(
                    test_id="playwright_runtime",
                    test_name="Playwright runtime",
                    description="Playwright launch/runtime failure",
                    category="functional",
                    priority=1,
                    target_page_id="",
                    coverage_signature="playwright_runtime",
                    result="error",
                    duration_seconds=0.0,
                    failure_reason=str(e),
                )
            ]
        except Exception as e:
            logger.error("Executor bootstrap failed before/while launching browser: %s", e)
            test_results = [
                TestResult(
                    test_id="executor_bootstrap",
                    test_name="Executor bootstrap",
                    description="Playwright/browser initialization",
                    category="functional",
                    priority=1,
                    target_page_id="",
                    coverage_signature="executor_bootstrap",
                    result="error",
                    duration_seconds=0.0,
                    failure_reason=str(e),
                )
            ]

        duration = time.time() - start_time
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        run_result = RunResult(
            run_id=self.run_id,
            plan_id=plan.plan_id,
            started_at=started_at,
            completed_at=completed_at,
            target_url=plan.target_url,
            total_tests=len(test_results),
            passed=sum(1 for r in test_results if r.result == "pass"),
            failed=sum(1 for r in test_results if r.result == "fail"),
            skipped=sum(1 for r in test_results if r.result == "skip"),
            errors=sum(1 for r in test_results if r.result == "error"),
            duration_seconds=round(duration, 2),
            test_results=test_results,
            step_retries=self.step_retries,
        )

        logger.info(
            "Execution complete: %d passed, %d failed, %d skipped, %d errors (%.1fs)",
            run_result.passed, run_result.failed, run_result.skipped,
            run_result.errors, duration,
        )
        return run_result

    @staticmethod
    def _find_video_file(video_dir: Path) -> str | None:
        """Find the .webm video file in a directory after context close."""
        try:
            for f in video_dir.iterdir():
                if f.suffix == ".webm":
                    return str(f)
        except OSError:
            pass
        return None

    @staticmethod
    def _counts_as_critical_failure(result: TestResult, tc: TestCase) -> bool:
        """Failed/error tests on critical-priority or security work count toward early exit."""
        if result.result not in ("fail", "error"):
            return False
        if tc.priority <= 1:
            return True
        if tc.category == "security":
            return True
        return False

    @staticmethod
    def _session_invalidated(result: TestResult) -> bool:
        """Check if a test likely invalidated the auth session (e.g. logout)."""
        if not result.evidence or not result.evidence.network_log:
            return False
        for entry in result.evidence.network_log:
            url = (entry.get("url") or "").lower()
            method = (entry.get("method") or "").upper()
            if method == "POST" and any(
                kw in url for kw in ("logout", "signout", "sign-out", "log-out")
            ):
                return True
        return False

    async def _run_test(
        self,
        context,
        test_case: TestCase,
        baseline_dir: Path | None,
        *,
        emit: PipelineEmit | None = None,
    ) -> TestResult:
        """Run a single test case with full step/assertion detail recording."""
        tc = test_case
        if self.config.skip_low_value_assertions:
            filtered = [a for a in tc.assertions if a.assertion_type not in LOW_VALUE_ASSERTION_TYPES]
            if len(filtered) < len(tc.assertions):
                logger.debug(
                    "Test %s: skipping %d low-value assertion(s)",
                    tc.test_id,
                    len(tc.assertions) - len(filtered),
                )
            tc = tc.model_copy(update={"assertions": filtered})
        test_start = time.time()
        evidence_dir = self.run_dir / "evidence" / tc.test_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Per-action selector timeout from config (distinct from overall test timeout)
        selector_timeout_ms = self.config.selector_timeout_seconds * 1000

        # Resolve dynamic variables (e.g. {{$timestamp}}) once for the entire
        # test case so preconditions and steps share the same values.
        resolve_dynamic_vars_for_test_case(tc.preconditions + tc.steps)

        required_tools = tool_names_for_test_case(tc)
        missing = sorted(t for t in required_tools if t not in TOOL_REGISTRY)
        if missing:
            logger.warning(
                "Test %s requires unregistered tools: %s",
                tc.test_id,
                missing,
            )
        logger.debug("Test %s tool set: %s", tc.test_id, sorted(required_tools))

        collector = EvidenceCollector(evidence_dir)
        evaluator = EvaluatorAgent(scan_task=self.config.scan_task)
        fallback_handler = None
        if self.ai_client:
            fallback_handler = FallbackHandler(
                self.ai_client, self.config.ai_max_fallback_calls_per_test
            )

        screenshots = []
        fallback_records = []
        precondition_results = []
        step_results = []
        assertion_results_list = []
        qa_defects_by_page: list[dict[str, Any]] = []
        qa_log_mark = 0

        page = await context.new_page()
        collector.setup_listeners(page)

        if emit:
            try:
                await emit(
                    "execution",
                    "test_start",
                    {"test_id": tc.test_id, "name": tc.name},
                )
            except Exception:
                pass

        try:
            logger.info("Executing actions")

            async def _qa_emit(msg: str) -> None:
                if emit:
                    try:
                        await emit(
                            "execution",
                            "step",
                            {
                                "test_id": tc.test_id,
                                "phase": "qa_action",
                                "message": msg,
                            },
                        )
                    except Exception:
                        pass

            async def _after_navigate_qa() -> None:
                nonlocal qa_log_mark
                slice_logs = collector.console_logs[qa_log_mark:]
                qa_log_mark = len(collector.console_logs)
                defects = await collect_console_defects_light(
                    page,
                    _qa_emit,
                    extra_console_lines=slice_logs or None,
                )
                qa_defects_by_page.append({
                    "page_url": page.url,
                    "defects": defects,
                })

            # === PRECONDITIONS ===
            if tc.preconditions:
                logger.debug("  Running %d preconditions...", len(tc.preconditions))
            for i, action in enumerate(tc.preconditions):
                logger.debug("  Precondition %d/%d: %s %s",
                             i + 1, len(tc.preconditions), action.action_type,
                             action.description or action.selector or "")
                if emit:
                    try:
                        await emit(
                            "execution",
                            "step",
                            {
                                "test_id": tc.test_id,
                                "step_index": i,
                                "phase": "precondition",
                                "action_type": action.action_type,
                            },
                        )
                    except Exception:
                        pass
                step_screenshot = None
                try:
                    await run_action(page, action, timeout=selector_timeout_ms)
                    precondition_results.append(StepResult(
                        step_index=i, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="pass",
                        screenshot_path=None,
                    ))
                    if action.action_type == "navigate":
                        await _after_navigate_qa()
                except Exception as e:
                    step_screenshot = await collector.take_screenshot(page, f"precond_{i}_fail")
                    if step_screenshot:
                        screenshots.append(step_screenshot)
                    precondition_results.append(StepResult(
                        step_index=i, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="fail",
                        error_message=str(e), screenshot_path=step_screenshot,
                    ))
                    logger.warning("Precondition %d failed: %s", i, e)

            # === TEST STEPS ===
            logger.debug("  Running %d test steps...", len(tc.steps))
            aborted = False
            for step_idx, action in enumerate(tc.steps):
                if aborted:
                    step_results.append(StepResult(
                        step_index=step_idx, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="skip",
                        error_message="Skipped due to earlier abort",
                    ))
                    continue

                logger.debug("  Step %d/%d: %s %s",
                             step_idx + 1, len(tc.steps), action.action_type,
                             action.description or action.selector or "")
                if emit:
                    try:
                        await emit(
                            "execution",
                            "step",
                            {
                                "test_id": tc.test_id,
                                "step_index": step_idx,
                                "phase": "step",
                                "action_type": action.action_type,
                            },
                        )
                    except Exception:
                        pass
                if action.action_type == "navigate":
                    logger.info("Navigating to URL")
                step_screenshot = None
                step_completed = False
                last_e: Exception | None = None
                last_fail_screenshot: str | None = None

                max_att = max(1, int(getattr(self.config, "step_max_evaluator_attempts", 2) or 2))
                for attempt in range(1, max_att + 1):
                    try:
                        await run_action(page, action, timeout=selector_timeout_ms)
                        actual_dict = {
                            "status": "pass",
                            "step_status": "pass",
                            "action_type": action.action_type,
                        }
                        evaluation = await evaluator.evaluate_step(
                            expected_outcome=action.description or "",
                            actual_result=actual_dict,
                            page_url=page.url or "",
                            action_performed=_action_summary_for_eval(action),
                            step_type="test_step",
                            test_id=tc.test_id,
                        )
                        reason = evaluation.get("reason")
                        if evaluation.get("success"):
                            step_results.append(StepResult(
                                step_index=step_idx,
                                action_type=action.action_type,
                                selector=action.selector,
                                value=action.value,
                                description=action.description,
                                status="pass",
                                screenshot_path=None,
                                evaluation_reason=reason,
                            ))
                            step_completed = True
                            break
                        if evaluation.get("should_retry") and attempt < max_att:
                            await self._record_step_retry()
                            if emit:
                                try:
                                    await emit(
                                        "evaluator",
                                        "retry",
                                        {
                                            "test_id": tc.test_id,
                                            "step_index": step_idx,
                                            "attempt": attempt,
                                            "phase": "evaluation",
                                            "reason": reason or "",
                                        },
                                    )
                                except Exception:
                                    pass
                            logger.info(
                                "Step %d (test %s) outcome mismatch, retry %d/%d: %s",
                                step_idx,
                                tc.test_id,
                                attempt,
                                max_att,
                                reason,
                            )
                            continue
                        fail_screenshot = await collector.take_screenshot(
                            page, f"step_{step_idx}_fail"
                        )
                        if fail_screenshot:
                            screenshots.append(fail_screenshot)
                        step_results.append(StepResult(
                            step_index=step_idx,
                            action_type=action.action_type,
                            selector=action.selector,
                            value=action.value,
                            description=action.description,
                            status="fail",
                            error_message=reason or "Step did not meet expected outcome",
                            screenshot_path=fail_screenshot,
                            evaluation_reason=reason,
                        ))
                        step_completed = True
                        break
                    except Exception as e:
                        last_e = e
                        fail_screenshot = await collector.take_screenshot(
                            page, f"step_{step_idx}_fail"
                        )
                        last_fail_screenshot = fail_screenshot
                        actual_dict = {
                            "status": "fail",
                            "step_status": "fail",
                            "error": str(e),
                            "action_type": action.action_type,
                        }
                        evaluation = await evaluator.evaluate_step(
                            expected_outcome=action.description or "",
                            actual_result=actual_dict,
                            page_url=page.url or "",
                            action_performed=_action_summary_for_eval(action),
                            step_type="test_step",
                            test_id=tc.test_id,
                        )
                        reason = evaluation.get("reason")
                        if evaluation.get("should_retry") and attempt < max_att:
                            await self._record_step_retry()
                            if emit:
                                try:
                                    await emit(
                                        "evaluator",
                                        "retry",
                                        {
                                            "test_id": tc.test_id,
                                            "step_index": step_idx,
                                            "attempt": attempt,
                                            "phase": "action",
                                            "reason": str(e),
                                        },
                                    )
                                except Exception:
                                    pass
                            logger.info(
                                "Step %d (test %s) action failed, retry %d/%d: %s",
                                step_idx,
                                tc.test_id,
                                attempt,
                                max_att,
                                e,
                            )
                            continue
                        if fail_screenshot:
                            screenshots.append(fail_screenshot)
                        break

                if step_completed and action.action_type == "navigate":
                    await _after_navigate_qa()

                if not step_completed:
                    e = last_e
                    fail_screenshot = last_fail_screenshot
                    if fail_screenshot is None:
                        fail_screenshot = await collector.take_screenshot(
                            page, f"step_{step_idx}_fail"
                        )
                        if fail_screenshot:
                            screenshots.append(fail_screenshot)

                    # Try AI fallback
                    recovered = False
                    if fallback_handler and fallback_handler.budget_remaining > 0:
                        logger.debug("  Step %d failed, attempting AI fallback (%d attempts remaining)...",
                                     step_idx + 1, fallback_handler.budget_remaining)
                        dom = ""
                        try:
                            dom = await page.content()
                        except Exception:
                            pass

                        fb_response = fallback_handler.request_fallback(
                            test_context=f"Test: {tc.name}\nStep {step_idx}: {action.description}",
                            screenshot_path=fail_screenshot or "",
                            dom_snippet=dom[:3000],
                            console_errors=collector.console_logs[-5:],
                            original_action=action,
                        )
                        record = fallback_handler.to_record(step_idx, action.selector or "", fb_response)
                        fallback_records.append(record)

                        if fb_response.decision == "retry" and fb_response.new_selector:
                            retry_action = action.model_copy()
                            retry_action.selector = fb_response.new_selector
                            try:
                                await run_action(page, retry_action, timeout=selector_timeout_ms, smart_resolve=False)
                                step_results.append(StepResult(
                                    step_index=step_idx, action_type=action.action_type,
                                    selector=fb_response.new_selector, value=action.value,
                                    description=f"{action.description} (retried with new selector)",
                                    status="pass", screenshot_path=None,
                                ))
                                recovered = True
                                if retry_action.action_type == "navigate":
                                    await _after_navigate_qa()
                            except Exception:
                                pass
                        elif fb_response.decision == "adapt" and fb_response.new_action:
                            try:
                                await run_action(page, fb_response.new_action, timeout=selector_timeout_ms, smart_resolve=False)
                                step_results.append(StepResult(
                                    step_index=step_idx, action_type=fb_response.new_action.action_type,
                                    selector=fb_response.new_action.selector,
                                    value=fb_response.new_action.value,
                                    description=f"{action.description} (adapted: {fb_response.reasoning})",
                                    status="pass", screenshot_path=None,
                                ))
                                recovered = True
                                if fb_response.new_action.action_type == "navigate":
                                    await _after_navigate_qa()
                            except Exception:
                                pass
                        elif fb_response.decision == "abort":
                            step_results.append(StepResult(
                                step_index=step_idx, action_type=action.action_type,
                                selector=action.selector, value=action.value,
                                description=action.description, status="fail",
                                error_message=f"Aborted: {fb_response.reasoning}",
                                screenshot_path=fail_screenshot,
                            ))
                            aborted = True
                            continue

                    if not recovered:
                        step_results.append(StepResult(
                            step_index=step_idx, action_type=action.action_type,
                            selector=action.selector, value=action.value,
                            description=action.description, status="fail",
                            error_message=str(e), screenshot_path=fail_screenshot,
                        ))

            # Capture the actual page the browser is on after steps execute.
            # This may differ from target_page_id when tests navigate (e.g. login → dashboard).
            # Only track valid HTTP(S) URLs — skip about:blank, data:, etc.
            current_url = page.url
            if current_url.startswith(("http://", "https://")):
                actual_page_id = page_id_from_url(current_url)
            else:
                actual_page_id = tc.target_page_id
            if actual_page_id != tc.target_page_id and tc.target_page_id:
                logger.info("Test navigated: target_page_id=%s, actual page=%s (%s)",
                            tc.target_page_id, actual_page_id, current_url)

            # === ASSERTIONS ===
            logger.debug("  Checking %d assertions...", len(tc.assertions))
            passed_count = 0
            failed_count = 0
            failure_reasons = []

            for a_idx, assertion in enumerate(tc.assertions):
                logger.debug("  Assertion %d/%d: %s — %s",
                             a_idx + 1, len(tc.assertions),
                             assertion.assertion_type,
                             assertion.description or assertion.selector or "")
                result = await check_assertion(
                    page, assertion, evidence_dir, baseline_dir,
                    collector.console_logs, collector.network_log,
                    self.config, self.ai_client,
                    visual_registry=self.visual_registry,
                    visual_registry_manager=self.visual_registry_manager,
                    page_id=tc.target_page_id,
                    run_id=self.run_id,
                )
                ar = AssertionResultModel(
                    assertion_type=assertion.assertion_type,
                    selector=assertion.selector,
                    expected_value=assertion.expected_value,
                    description=assertion.description,
                    passed=result.passed,
                    message=result.message,
                )
                assertion_results_list.append(ar)

                # Collect viewport screenshots captured by screenshot_diff
                if result.screenshots:
                    screenshots.extend(result.screenshots)

                if result.passed:
                    passed_count += 1
                    logger.debug("  Assertion %d/%d: PASSED — %s",
                                 a_idx + 1, len(tc.assertions), result.message)
                else:
                    failed_count += 1
                    failure_reasons.append(f"{assertion.description}: {result.message}")
                    logger.debug("  Assertion %d/%d: FAILED — %s",
                                 a_idx + 1, len(tc.assertions), result.message)

            # Final screenshot only when useful (failures / visual / abort)
            if tc.category == "visual" or failed_count > 0 or aborted:
                s = await collector.take_screenshot(page, "final")
                if s:
                    screenshots.append(s)

            collector.save_logs()

            test_result_status = "pass" if failed_count == 0 and not aborted else "fail"
            if aborted and failed_count == 0:
                test_result_status = "error"

            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                actual_page_id=actual_page_id,
                actual_url=current_url if current_url.startswith(("http://", "https://")) else "",
                coverage_signature=tc.coverage_signature,
                result=test_result_status,
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason="; ".join(failure_reasons) if failure_reasons else None,
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
                assertions_passed=passed_count,
                assertions_failed=failed_count,
                assertions_total=len(tc.assertions),
                qa_defects_by_page=qa_defects_by_page,
            )

        except PlaywrightTimeoutError as e:
            logger.error("Playwright timeout in test %s: %s", tc.test_id, e)
            collector.save_logs()
            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                coverage_signature=tc.coverage_signature,
                result="error",
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason=f"Playwright timeout: {e}",
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
                qa_defects_by_page=qa_defects_by_page,
            )
        except PlaywrightError as e:
            logger.error("Playwright runtime error in test %s: %s", tc.test_id, e)
            collector.save_logs()
            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                coverage_signature=tc.coverage_signature,
                result="error",
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason=f"Playwright error: {e}",
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
                qa_defects_by_page=qa_defects_by_page,
            )
        except Exception as e:
            logger.error("Test %s crashed: %s", tc.test_id, e)
            collector.save_logs()
            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                coverage_signature=tc.coverage_signature,
                result="error",
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason=str(e),
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
                qa_defects_by_page=qa_defects_by_page,
            )
        finally:
            await page.close()
