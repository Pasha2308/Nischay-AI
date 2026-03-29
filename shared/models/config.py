"""Configuration models for the QA framework."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ViewportConfig(BaseModel):
    width: int = 1280
    height: int = 720
    name: str = "desktop"


class CrawlConfig(BaseModel):
    target_url: str = ""
    # Tuned for faster scans (<~2 min crawl); raise for deeper audits
    max_pages: int = 5
    max_depth: int = 2
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    auth_credentials: Optional[dict] = None
    auth_url: Optional[str] = None
    wait_for_idle: bool = False
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    user_agent: Optional[str] = None
    # 0 = no artificial delay between page loads
    inter_page_delay_ms: int = 0
    # 1 = sequential; 2–3 = parallel URL batches (faster discovery)
    parallel_crawl_workers: int = 2
    skip_sitemap: bool = True
    early_stop_key_pages: bool = True
    capture_page_screenshots: bool = False
    save_dom_snapshot: bool = False


class AuthConfig(BaseModel):
    login_url: str
    username: str
    password: str
    username_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""
    success_indicator: str = ""
    auto_detect: bool = True
    llm_fallback: bool = True

    @field_validator("password", mode="before")
    @classmethod
    def resolve_env_password(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("env:"):
            env_var = v[4:]
            resolved = os.environ.get(env_var)
            if resolved is None:
                raise ValueError(f"Environment variable '{env_var}' not set")
            return resolved
        return v


class FrameworkConfig(BaseModel):
    # Target
    target_url: str

    # fast: fewer tests, shorter timeouts, early exit; deep: full scan (higher limits, no early exit)
    scan_mode: Literal["fast", "deep"] = "fast"
    # Task bundle id (e.g. full_app_scan, quick_scan) or legacy full_app — expanded via TASK_GROUPS
    scan_task: str = "full_app_scan"
    # Optional explicit flow list (auth, browse, product, …); when set, overrides scan_task expansion
    flows: Optional[list[str]] = None
    # "micro" = single quick task via run_micro_task; otherwise full multi-flow scan
    task_type: Optional[str] = None
    micro_task: Optional[str] = None

    # Authentication
    auth: Optional[AuthConfig] = None
    # When True, run programmatic login on the target URL before crawling (shared browser context).
    requires_login: bool = False
    credentials: Optional[dict[str, str]] = None  # e.g. username, password

    # Crawl settings
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)

    # Test categories
    categories: list[str] = Field(
        default_factory=lambda: ["functional", "visual", "security"]
    )

    # Execution limits
    max_tests_per_run: int = 5
    max_execution_time_seconds: int = 90
    max_parallel_contexts: int = 3
    selector_timeout_seconds: int = 4
    # Evaluator step retries: 2 attempts = one initial try + one retry (was 3).
    step_max_evaluator_attempts: int = 2
    # Pipeline (shared browser): stop after this many critical failures (0 = disabled).
    executor_early_exit_critical_threshold: int = 3
    # Skip expensive / marginal assertions to reduce wall time (screenshot_diff, ai_evaluate, element_count).
    skip_low_value_assertions: bool = False

    # AI settings
    ai_provider: str = "anthropic"
    ai_model: str = "claude-opus-4-6"
    ai_base_url: Optional[str] = None
    ai_max_fallback_calls_per_test: int = 3
    ai_max_planning_tokens: int = 32000  # Increased to support large test plans

    # Coverage settings
    staleness_threshold_days: int = 7
    history_retention_runs: int = 20

    # Visual testing
    visual_diff_tolerance: float = 0.05
    viewports: list[ViewportConfig] = Field(
        default_factory=lambda: [
            ViewportConfig(width=1280, height=720, name="desktop"),
            ViewportConfig(width=768, height=1024, name="tablet"),
            ViewportConfig(width=375, height=812, name="mobile"),
        ]
    )

    # Security testing
    security_xss_payloads: list[str] = Field(
        default_factory=lambda: [
            '<script>alert(1)</script>',
            '"><img src=x onerror=alert(1)>',
            "javascript:alert(1)",
            "'-alert(1)-'",
            '<svg onload=alert(1)>',
        ]
    )
    security_max_probe_depth: int = 2

    # Reporting
    report_formats: list[str] = Field(default_factory=lambda: ["html", "json"])
    report_output_dir: str = "./qa-reports"
    capture_video: str = "on_failure"

    @field_validator("scan_mode", mode="before")
    @classmethod
    def normalize_scan_mode(cls, v: object) -> str:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("fast", "deep"):
                return s
            raise ValueError("scan_mode must be 'fast' or 'deep'")
        raise ValueError(f"scan_mode must be str, got {type(v).__name__}")

    @field_validator("capture_video", mode="before")
    @classmethod
    def normalize_capture_video(cls, v: str | bool) -> str:
        """Accept bool for backward compat; normalize to string enum."""
        if isinstance(v, bool):
            return "on_failure" if v else "off"
        if isinstance(v, str):
            v_lower = v.lower().strip()
            valid = {"off", "on_failure", "always"}
            if v_lower not in valid:
                raise ValueError(
                    f"capture_video must be one of {valid}, got '{v}'"
                )
            return v_lower
        raise ValueError(f"capture_video must be str or bool, got {type(v).__name__}")

    @field_validator("ai_provider", mode="before")
    @classmethod
    def normalize_ai_provider(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError(f"ai_provider must be str, got {type(v).__name__}")
        provider = v.strip().lower()
        valid = {"anthropic", "ollama"}
        if provider not in valid:
            raise ValueError(f"ai_provider must be one of {valid}, got '{v}'")
        return provider

    # Scope
    include_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)

    # Hints
    hints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _apply_scan_mode_presets(self) -> "FrameworkConfig":
        """scan_mode selects bundled execution limits (overrides individual field defaults)."""
        if not self.crawl.target_url:
            self.crawl.target_url = self.target_url
        if self.scan_mode == "fast":
            self.max_tests_per_run = 5
            self.max_execution_time_seconds = 90
            self.selector_timeout_seconds = 4
            self.step_max_evaluator_attempts = 2
            self.executor_early_exit_critical_threshold = 3
            self.skip_low_value_assertions = True
        else:
            self.max_tests_per_run = 10
            self.max_execution_time_seconds = 1800
            self.selector_timeout_seconds = 6
            self.step_max_evaluator_attempts = 3
            self.executor_early_exit_critical_threshold = 0
            self.skip_low_value_assertions = False
        return self

    @classmethod
    def load(cls, path: str | Path) -> "FrameworkConfig":
        """Load config from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def save(self, path: str | Path) -> None:
        """Save config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
