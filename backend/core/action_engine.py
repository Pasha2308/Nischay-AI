"""Lightweight console and resource checks for loaded pages."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from playwright.async_api import Page

from backend.core.defects import make_defect

logger = logging.getLogger(__name__)

EmitEvent = Optional[Callable[[str], Awaitable[None]]]


async def capture_console_errors(
    page: Page,
    emit_event: EmitEvent | None = None,
    *,
    console_buffer: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Console.error lines (HIGH) + failed resource hints from performance API."""
    _ = emit_event
    defects: list[dict[str, Any]] = []
    url = page.url
    seen: set[str] = set()

    if console_buffer:
        for line in console_buffer:
            key = line[:2000]
            if key in seen:
                continue
            seen.add(key)
            defects.append(
                make_defect(
                    defect="console_error",
                    title=f"Client-side error in console on {url}",
                    description=f"Console error: {line[:2000]}",
                    element="browser console",
                    user_view="User may see broken UI behavior or missing functionality due to a client-side error.",
                    how_to_fix="Fix the reported JS error at its source and add a regression test for the failing path. Verify no console errors remain on page load and key interactions.",
                    severity="medium",
                    business_impact="trust",
                    page_url=url,
                    extra={"type": "browser_console"},
                )
            )

    try:
        failed_res = await page.evaluate("""() => {
          const out = [];
          try {
            performance.getEntriesByType('resource').forEach((r) => {
              const n = r.name || '';
              if (!n || !(n.endsWith('.js') || n.endsWith('.css'))) return;
              if (r.transferSize === 0 && r.decodedBodySize === 0 && r.duration > 50)
                out.push(n);
            });
          } catch (e) {}
          return out.slice(0, 20);
        }""")
        for name in failed_res:
            defects.append(
                make_defect(
                    defect="console_error",
                    title=f"Possible failed asset load on {url}",
                    description=f"Possible failed script/style load (performance entries): {str(name)[:200]}",
                    element=str(name)[:200],
                    user_view="Parts of the page may not render or behave correctly if scripts/styles fail to load.",
                    how_to_fix="Verify the asset URL returns 200, correct content-type, and is not blocked by CSP/CDN. Ensure build pipeline publishes the referenced file.",
                    severity="low",
                    business_impact="performance",
                    page_url=url,
                    extra={"type": "failed_resource"},
                )
            )
    except Exception as e:
        logger.debug("capture_console_errors: %s", e)
    return defects


def merge_console_log_defects(page_url: str, console_lines: list[str]) -> list[dict[str, Any]]:
    """Turn recent [error] console lines into defect dicts."""
    defects: list[dict[str, Any]] = []
    for line in console_lines:
        low = line.lower()
        if "[error]" in low or " uncaught " in low or "typeerror" in low or "syntaxerror" in low:
            defects.append(
                make_defect(
                    defect="console_error",
                    title=f"Client-side error in console on {page_url}",
                    description=f"Console error: {line[:500]}",
                    element="browser console",
                    user_view="User may encounter broken UI or missing functionality due to a JS error.",
                    how_to_fix="Fix the exception (check stack/message), add guards for undefined values, and ensure bundles/load order are correct. Re-test the flow that triggers it.",
                    severity="medium",
                    business_impact="trust",
                    page_url=page_url,
                    extra={"type": "browser_console"},
                )
            )
    return defects


async def collect_console_defects_light(
    page: Page,
    emit_event: EmitEvent | None = None,
    *,
    extra_console_lines: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Console errors from a short-lived listener, optional merged log lines, failed resources."""
    console_buffer: list[str] = []

    def _on_console(msg: Any) -> None:
        if getattr(msg, "type", None) == "error":
            console_buffer.append(str(msg.text or ""))

    page.on("console", _on_console)
    try:
        defects = await capture_console_errors(page, emit_event, console_buffer=console_buffer)
        if extra_console_lines:
            defects.extend(merge_console_log_defects(page.url, extra_console_lines))
        return defects
    finally:
        try:
            page.remove_listener("console", _on_console)
        except Exception:
            pass
