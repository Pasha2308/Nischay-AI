"""Active QA checks run after navigation (forms, DOM, nav, performance, console)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

EmitEvent = Optional[Callable[[str], Awaitable[None]]]

_MAX_BUTTON_CLICKS = 12
_MAX_NAV_LINK_SAMPLES = 5
_MAX_FORMS_SUBMIT_TEST = 2
_SUCCESS_HINTS = (
    "thank you",
    "thanks",
    "success",
    "submitted",
    "confirmed",
    "sent",
    "received",
    "your message",
    "we'll be in touch",
)

_CTA_KEYWORDS = ("buy", "checkout", "submit")


async def _emit(emit_event: EmitEvent, message: str) -> None:
    if emit_event:
        try:
            await emit_event(message)
        except Exception:
            pass


async def test_forms(
    page: Page,
    emit_event: EmitEvent,
    log_action: Any = None,
    log_bracketed: Any = None,
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    url = page.url
    start_url = page.url
    await _emit(emit_event, "QA: test_forms — scanning forms")
    try:
        data = await page.evaluate("""() => {
          const forms = Array.from(document.querySelectorAll('form'));
          return forms.map((f, i) => ({
            index: i,
            action: f.getAttribute('action') || '',
            method: (f.getAttribute('method') || 'get').toLowerCase(),
            inputs: f.querySelectorAll('input, textarea, select').length,
            hasSubmit: !!f.querySelector('button[type="submit"], input[type="submit"]'),
          }));
        }""")
        for f in data:
            if f.get("inputs", 0) == 0:
                defects.append({
                    "defect": "empty_form",
                    "type": "form",
                    "page_url": url,
                    "description": f"Form #{f.get('index', 0)} has no input fields",
                })
            if not f.get("hasSubmit") and f.get("inputs", 0) > 0:
                defects.append({
                    "defect": "form_missing_submit",
                    "type": "form",
                    "page_url": url,
                    "description": f"Form #{f.get('index', 0)} has inputs but no submit control",
                })

        # Submit attempt: URL change or success copy after submit
        forms_count = await page.locator("form").count()
        for fi in range(min(forms_count, _MAX_FORMS_SUBMIT_TEST)):
            form = page.locator("form").nth(fi)
            try:
                if await form.locator('input[type="password"]').count() > 0:
                    continue
                submit = form.locator(
                    'button[type="submit"], input[type="submit"], button:not([type])'
                ).first
                if await submit.count() == 0:
                    continue
                text_inputs = form.locator(
                    'input[type="text"], input[type="email"], input[type="search"], '
                    'input:not([type]), textarea'
                )
                tn = await text_inputs.count()
                for j in range(min(tn, 4)):
                    try:
                        await text_inputs.nth(j).fill("qa-test@example.com", timeout=800)
                    except Exception:
                        pass
                before_url = page.url
                if log_bracketed:

                    async def _form_submit() -> None:
                        await submit.click(timeout=5000)
                        await page.wait_for_load_state("domcontentloaded", timeout=8000)
                        await asyncio.sleep(0.4)

                    await log_bracketed(
                        page,
                        phase="execute",
                        action_type="submit",
                        description=f"test_forms probe submit form {fi}",
                        target_url=before_url,
                        coro=_form_submit,
                    )
                else:
                    await submit.click(timeout=5000)
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
                    await asyncio.sleep(0.4)
                after_url = page.url
                try:
                    body = (await page.inner_text("body", timeout=5000)).lower()
                except Exception:
                    body = ""
                ok = before_url != after_url or any(h in body for h in _SUCCESS_HINTS)
                if not ok:
                    defects.append({
                        "defect": "form_submission_failed",
                        "type": "form",
                        "severity": "medium",
                        "page_url": page.url,
                        "description": (
                            f"Form #{fi}: no URL change and no obvious success message after submit"
                        ),
                    })
                if page.url != start_url:
                    try:
                        if log_bracketed:
                            _su = start_url

                            async def _restore_start() -> None:
                                await page.goto(
                                    _su,
                                    wait_until="domcontentloaded",
                                    timeout=25000,
                                )

                            await log_bracketed(
                                page,
                                phase="execute",
                                action_type="navigate",
                                description="test_forms restore start_url after submit",
                                target_url=start_url,
                                coro=_restore_start,
                            )
                        else:
                            await page.goto(
                                start_url,
                                wait_until="domcontentloaded",
                                timeout=25000,
                            )
                    except Exception as e:
                        logger.debug("test_forms: could not restore URL: %s", e)
            except Exception as e:
                logger.debug("test_forms submit probe %s: %s", fi, e)
    except Exception as e:
        logger.debug("test_forms: %s", e)
        await _emit(emit_event, f"QA: test_forms — error: {str(e)[:80]}")
    await _emit(emit_event, "QA: test_forms — done")
    return defects


async def scan_broken_elements(
    page: Page,
    emit_event: EmitEvent,
    log_action: Any = None,
    log_bracketed: Any = None,
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    url = page.url
    start_url = page.url
    await _emit(emit_event, "QA: scan_broken_elements — scanning DOM")
    try:
        broken = await page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('img').forEach((img, i) => {
            const src = img.getAttribute('src') || '';
            if (!src.trim()) out.push({ kind: 'img_empty_src', index: i });
          });
          document.querySelectorAll('a[href]').forEach((a, i) => {
            const h = (a.getAttribute('href') || '').trim();
            if (h === '' || h === '#') out.push({ kind: 'anchor_empty_href', index: i });
          });
          return out;
        }""")
        for b in broken:
            defects.append({
                "defect": "broken_element",
                "type": b.get("kind", "unknown"),
                "page_url": url,
                "description": str(b),
            })

        buttons = page.locator("button:visible")
        n = await buttons.count()
        for i in range(min(n, _MAX_BUTTON_CLICKS)):
            try:
                u0 = page.url
                btn = buttons.nth(i)
                _bi = btn
                if log_bracketed:

                    async def _btn_click() -> None:
                        await _bi.click(timeout=1000)
                        await asyncio.sleep(0.15)

                    await log_bracketed(
                        page,
                        phase="execute",
                        action_type="click",
                        description=f"scan_broken_elements button probe {i}",
                        target_url=u0,
                        coro=_btn_click,
                    )
                else:
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.15)
                if page.url != u0:
                    try:
                        if log_bracketed:

                            async def _go_back() -> None:
                                await page.go_back(
                                    wait_until="domcontentloaded", timeout=20000
                                )

                            await log_bracketed(
                                page,
                                phase="execute",
                                action_type="navigate",
                                description="scan_broken_elements go_back after button",
                                target_url=page.url,
                                coro=_go_back,
                            )
                        else:
                            await page.go_back(
                                wait_until="domcontentloaded", timeout=20000
                            )
                    except Exception:
                        try:
                            if log_bracketed:
                                _st = start_url

                                async def _goto_start() -> None:
                                    await page.goto(
                                        _st,
                                        wait_until="domcontentloaded",
                                        timeout=20000,
                                    )

                                await log_bracketed(
                                    page,
                                    phase="execute",
                                    action_type="navigate",
                                    description="scan_broken_elements restore start_url",
                                    target_url=start_url,
                                    coro=_goto_start,
                                )
                            else:
                                await page.goto(
                                    start_url,
                                    wait_until="domcontentloaded",
                                    timeout=20000,
                                )
                        except Exception:
                            pass
            except Exception:
                defects.append({
                    "defect": "unresponsive_button",
                    "type": "interaction",
                    "severity": "medium",
                    "page_url": page.url,
                    "description": f"Button index {i} did not respond to click within 1000ms",
                })
    except Exception as e:
        logger.debug("scan_broken_elements: %s", e)
        await _emit(emit_event, f"QA: scan_broken_elements — error: {str(e)[:80]}")
    await _emit(emit_event, "QA: scan_broken_elements — done")
    return defects


async def validate_navigation(
    page: Page,
    emit_event: EmitEvent,
    log_action: Any = None,
    log_bracketed: Any = None,
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    url = page.url
    start_url = page.url
    await _emit(emit_event, "QA: validate_navigation — checking links")
    try:
        nav = await page.evaluate("""() => {
          const links = Array.from(document.querySelectorAll('a[href]'));
          const hrefs = links.map(a => (a.getAttribute('href') || '').trim());
          const empty = hrefs.filter(h => !h || h === '#').length;
          return { total: links.length, emptyHrefs: empty };
        }""")
        if nav.get("total", 0) == 0:
            defects.append({
                "defect": "navigation_sparse",
                "type": "navigation",
                "page_url": url,
                "description": "No anchor links found on page",
            })
        elif nav.get("emptyHrefs", 0) > 0:
            defects.append({
                "defect": "navigation_empty_hrefs",
                "type": "navigation",
                "page_url": url,
                "description": f"{nav['emptyHrefs']} link(s) with empty or # href",
            })

        hrefs = await page.evaluate("""() => {
          const origin = location.origin;
          const seen = new Set();
          const out = [];
          document.querySelectorAll('a[href]').forEach((a) => {
            let h = (a.getAttribute('href') || '').trim();
            if (!h || h.startsWith('#') || h.toLowerCase().startsWith('javascript:')) return;
            if (h.startsWith('mailto:') || h.startsWith('tel:')) return;
            try {
              const u = new URL(h, location.href);
              if (u.origin !== origin) return;
              const abs = u.href.split('#')[0];
              if (seen.has(abs)) return;
              seen.add(abs);
              out.push(abs);
            } catch (e) {}
          });
          return out;
        }""")
        sample = list(hrefs)[:_MAX_NAV_LINK_SAMPLES]
        for href in sample:
            if href.rstrip("/") == start_url.rstrip("/"):
                continue
            try:
                if log_bracketed:

                    async def _nav_sample(h: str = href) -> None:
                        await page.goto(h, wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(0.2)

                    await log_bracketed(
                        page,
                        phase="execute",
                        action_type="navigate",
                        description="validate_navigation sample link",
                        target_url=href,
                        coro=_nav_sample,
                    )
                else:
                    await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(0.2)
            except Exception as e:
                defects.append({
                    "defect": "navigation_load_failed",
                    "type": "navigation",
                    "severity": "high",
                    "page_url": href,
                    "description": f"Navigation failed: {str(e)[:300]}",
                })
            try:
                if log_bracketed:
                    _rsu = start_url

                    async def _restore_nav() -> None:
                        await page.goto(
                            _rsu, wait_until="domcontentloaded", timeout=20000
                        )

                    await log_bracketed(
                        page,
                        phase="execute",
                        action_type="navigate",
                        description="validate_navigation restore start_url",
                        target_url=start_url,
                        coro=_restore_nav,
                    )
                else:
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                logger.debug("validate_navigation: restore %s: %s", start_url, e)
                break
    except Exception as e:
        logger.debug("validate_navigation: %s", e)
        await _emit(emit_event, f"QA: validate_navigation — error: {str(e)[:80]}")
    await _emit(emit_event, "QA: validate_navigation — done")
    return defects


async def capture_performance_signals(
    page: Page, emit_event: EmitEvent, log_action: Any = None
) -> dict[str, Any]:
    defects: list[dict[str, Any]] = []
    url = page.url
    await _emit(emit_event, "QA: capture_performance_signals — measuring")
    try:
        timing = await page.evaluate("""() => {
          const p = performance.timing || {};
          const nav = performance.getEntriesByType('navigation')[0];
          const load = (nav && nav.loadEventEnd && nav.fetchStart)
            ? nav.loadEventEnd - nav.fetchStart
            : (p.loadEventEnd && p.navigationStart ? p.loadEventEnd - p.navigationStart : null);
          return { loadMs: load };
        }""")
        load_ms = timing.get("loadMs")
        if load_ms is not None and load_ms > 8000:
            defects.append({
                "defect": "slow_page_load",
                "type": "performance",
                "page_url": url,
                "description": f"Load interval ~{int(load_ms)}ms exceeds 8000ms threshold",
            })
    except Exception as e:
        logger.debug("capture_performance_signals: %s", e)
        await _emit(emit_event, f"QA: capture_performance_signals — error: {str(e)[:80]}")
    await _emit(emit_event, "QA: capture_performance_signals — done")
    return {"defects": defects}


async def check_missing_cta(page: Page, emit_event: EmitEvent) -> list[dict[str, Any]]:
    """Flag pages with no obvious primary CTA (buy / checkout / submit)."""
    defects: list[dict[str, Any]] = []
    url = page.url
    await _emit(emit_event, "QA: check_missing_cta — scanning CTAs")
    try:
        has_cta = await page.evaluate(
            """() => {
              const keys = ['buy', 'checkout', 'submit'];
              const nodes = Array.from(
                document.querySelectorAll('button, [role="button"], input[type="submit"], a')
              );
              return nodes.some((el) => {
                const t = (el.innerText || el.value || el.getAttribute('aria-label') || '')
                  .toLowerCase();
                return keys.some((k) => t.includes(k));
              });
            }"""
        )
        if not has_cta:
            defects.append({
                "defect": "missing_primary_action",
                "type": "cta",
                "severity": "high",
                "page_url": url,
                "description": 'No button/link text contains "buy", "checkout", or "submit"',
            })
    except Exception as e:
        logger.debug("check_missing_cta: %s", e)
        await _emit(emit_event, f"QA: check_missing_cta — error: {str(e)[:80]}")
    await _emit(emit_event, "QA: check_missing_cta — done")
    if log_action:
        await log_action(
            page,
            phase="execute",
            action_type="detect",
            description="check_missing_cta",
            target_url=url,
        )
    return defects


async def collect_active_qa_defects_after_navigation(
    page: Page,
    emit_event: EmitEvent,
    *,
    console_log_lines: list[str] | None = None,
    log_action: Any | None = None,
    log_bracketed: Any | None = None,
) -> list[dict[str, Any]]:
    """After ``page.goto`` / navigation: run QA checks in order, merge into one defect list."""
    console_buffer: list[str] = []

    def _on_console(msg: Any) -> None:
        if msg.type == "error":
            console_buffer.append(str(msg.text or ""))

    page.on("console", _on_console)
    try:
        defects: list[dict[str, Any]] = []
        defects.extend(
            await test_forms(
                page, emit_event, log_action=log_action, log_bracketed=log_bracketed
            )
        )
        defects.extend(
            await scan_broken_elements(
                page, emit_event, log_action=log_action, log_bracketed=log_bracketed
            )
        )
        defects.extend(
            await validate_navigation(
                page, emit_event, log_action=log_action, log_bracketed=log_bracketed
            )
        )
        defects.extend(await check_missing_cta(page, emit_event, log_action=log_action))
        perf = await capture_performance_signals(page, emit_event, log_action=log_action)
        defects.extend(perf["defects"])
        defects.extend(
            await capture_console_errors(page, emit_event, console_buffer=console_buffer)
        )
        if log_action:
            await log_action(
                page,
                phase="execute",
                action_type="detect",
                description="collect_active_qa_defects_after_navigation complete",
                target_url=page.url,
            )
        if console_log_lines:
            defects.extend(merge_console_log_defects(page.url, console_log_lines))
        return defects
    finally:
        try:
            page.remove_listener("console", _on_console)
        except Exception:
            pass


async def capture_console_errors(
    page: Page,
    emit_event: EmitEvent | None = None,
    *,
    console_buffer: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Console.error lines (HIGH) + failed resource hints from performance API."""
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
