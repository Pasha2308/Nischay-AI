"""
Screenshot manager for Nischay AI.
Captures and stores Playwright screenshots during QA execution.
Screenshots stored at: runs/{run_id}/screenshots/
Served via GET /api/runs/{run_id}/screenshots/{filename}.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ScreenshotManager:
    """Async screenshot capture aligned with Playwright ``Page`` API."""

    def __init__(self, run_id: str) -> None:
        self.run_id = (run_id or "").strip() or "unknown_run"
        self.base_dir = Path("runs") / self.run_id / "screenshots"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots: list[dict[str, object]] = []

    async def capture_page(
        self, page: Page, label: str, page_url: str = ""
    ) -> dict[str, object] | None:
        """
        Capture a full-page screenshot.
        Returns metadata dict or None if capture fails.
        """
        try:
            safe_label = (label or "page").replace("/", "_").replace(" ", "_")
            timestamp = int(time.time() * 1000)
            filename = f"{safe_label}_{timestamp}.png"
            filepath = self.base_dir / filename

            await page.screenshot(
                path=str(filepath),
                full_page=True,
                timeout=5000,
            )

            rel = f"/api/runs/{self.run_id}/screenshots/{filename}"
            metadata: dict[str, object] = {
                "filename": filename,
                "label": label,
                "page_url": page_url or page.url,
                "path": str(filepath),
                "url_path": rel,
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "type": "page",
            }
            self.screenshots.append(metadata)
            self._save_index()
            return metadata
        except Exception as e:
            logger.warning("[SCREENSHOT] Failed to capture '%s': %s", label, e)
            return None

    async def capture_element(
        self, page: Page, selector: str, label: str, page_url: str = ""
    ) -> dict[str, object] | None:
        """
        Capture a specific element screenshot for issue evidence.
        Falls back to viewport screenshot if element not found.
        """
        try:
            safe_label = (label or "issue").replace("/", "_").replace(" ", "_")
            timestamp = int(time.time() * 1000)
            filename = f"issue_{safe_label}_{timestamp}.png"
            filepath = self.base_dir / filename

            sel = (selector or "body").strip() or "body"
            try:
                element = page.locator(sel).first
                await element.screenshot(path=str(filepath), timeout=3000)
            except Exception:
                await page.screenshot(path=str(filepath), full_page=False, timeout=5000)

            rel = f"/api/runs/{self.run_id}/screenshots/{filename}"
            metadata: dict[str, object] = {
                "filename": filename,
                "label": label,
                "page_url": page_url or page.url,
                "path": str(filepath),
                "url_path": rel,
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "type": "issue",
                "selector": sel,
            }
            self.screenshots.append(metadata)
            self._save_index()
            return metadata
        except Exception as e:
            logger.warning("[SCREENSHOT] Element capture failed '%s': %s", label, e)
            return None

    def _save_index(self) -> None:
        """Persist screenshot index for API list endpoint."""
        index_path = self.base_dir / "index.json"
        try:
            index_path.write_text(
                json.dumps(self.screenshots, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Could not write screenshot index: %s", e)

    def get_all(self) -> list[dict[str, object]]:
        """Return all captured screenshot metadata."""
        return list(self.screenshots)

    def get_for_url(self, page_url: str) -> list[dict[str, object]]:
        """Return screenshots whose page_url matches."""
        return [s for s in self.screenshots if str(s.get("page_url") or "") == page_url]
