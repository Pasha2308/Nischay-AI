"""Lightweight console and resource checks for loaded pages."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from playwright.async_api import Page

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
            defects.append({
                "defect": "console_error",
                "type": "browser_console",
                "severity": "high",
                "page_url": url,
                "description": line[:2000],
            })

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
            defects.append({
                "defect": "console_error",
                "type": "failed_resource",
                "severity": "medium",
                "page_url": url,
                "description": f"Possible failed script/style load: {name[:200]}",
            })
    except Exception as e:
        logger.debug("capture_console_errors: %s", e)
    return defects


def merge_console_log_defects(page_url: str, console_lines: list[str]) -> list[dict[str, Any]]:
    """Turn recent [error] console lines into defect dicts."""
    defects: list[dict[str, Any]] = []
    for line in console_lines:
        low = line.lower()
        if "[error]" in low or " uncaught " in low or "typeerror" in low or "syntaxerror" in low:
            defects.append({
                "defect": "console_error",
                "type": "browser_console",
                "severity": "high",
                "page_url": page_url,
                "description": line[:500],
            })
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
