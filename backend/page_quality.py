"""Page-level quality checks: accessibility, performance hints, mixed content (deterministic).

Runs in the browser context via Playwright Page — no eval() of user code.
"""

from __future__ import annotations

import time
from typing import Any

from playwright.async_api import Page


def _issue(
    *,
    type_: str,
    severity: str,
    page_url: str,
    element_selector: str,
    description: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "type": type_,
        "severity": severity,
        "page_url": page_url,
        "element_selector": element_selector,
        "description": description,
        "evidence": evidence,
    }


async def collect_page_quality_issues(
    page: Page,
    *,
    navigation_start_ms: float | None = None,
) -> list[dict[str, Any]]:
    """Return structured issues for the current page (best-effort)."""
    issues: list[dict[str, Any]] = []
    url = page.url

    # Slow load (>3s from optional navigation start)
    if navigation_start_ms is not None:
        elapsed = (time.time() - navigation_start_ms) * 1000
        if elapsed > 3000:
            issues.append(
                _issue(
                    type_="slow_page_load",
                    severity="medium",
                    page_url=url,
                    element_selector="",
                    description=f"Page load exceeded 3s ({elapsed:.0f}ms)",
                    evidence=f"navigation_timing_ms={elapsed:.0f}",
                )
            )

    # Broken images + missing alt (DOM scan)
    try:
        img_report = await page.evaluate(
            """() => {
              const imgs = Array.from(document.querySelectorAll('img'));
              return imgs.map((img, i) => ({
                i,
                src: img.getAttribute('src') || '',
                alt: img.getAttribute('alt'),
                w: img.naturalWidth,
                h: img.naturalHeight,
                complete: img.complete
              }));
            }"""
        )
        for row in img_report:
            sel = f"img:nth-of-type({row['i'] + 1})"
            src = (row.get("src") or "")[:500]
            if row.get("complete") and row.get("w") == 0 and row.get("h") == 0 and src:
                issues.append(
                    _issue(
                        type_="broken_image",
                        severity="high",
                        page_url=url,
                        element_selector=sel,
                        description="Image appears broken (0×0 natural size)",
                        evidence=f"src={src}",
                    )
                )
            alt = row.get("alt")
            if alt is None or str(alt).strip() == "":
                issues.append(
                    _issue(
                        type_="missing_alt_text",
                        severity="low",
                        page_url=url,
                        element_selector=sel,
                        description="Image missing alternative text",
                        evidence=f"src={src}",
                    )
                )
    except Exception:
        pass

    # Mixed content: https page loading http resources
    try:
        if url.startswith("https://"):
            mixed = await page.evaluate(
                """() => {
                  const bad = [];
                  document.querySelectorAll('img[src^="http:"], script[src^="http:"], link[href^="http:"]').forEach(el => {
                    bad.push(el.tagName + ':' + (el.src || el.href || ''));
                  });
                  return bad.slice(0, 20);
                }"""
            )
            for m in mixed:
                issues.append(
                    _issue(
                        type_="mixed_content",
                        severity="high",
                        page_url=url,
                        element_selector="",
                        description="Active mixed content (HTTP asset on HTTPS page)",
                        evidence=m[:300],
                    )
                )
    except Exception:
        pass

    # Empty form labels (input not associated with label)
    try:
        unlabeled = await page.evaluate(
            """() => {
              const out = [];
              document.querySelectorAll('input, select, textarea').forEach((el, i) => {
                const id = el.id;
                const aria = el.getAttribute('aria-label');
                const pl = el.getAttribute('placeholder');
                if (aria && aria.trim()) return;
                if (pl && pl.trim()) return;
                if (id && document.querySelector('label[for="' + id + '"]')) return;
                if (el.closest('label')) return;
                out.push(el.tagName + '#' + (id || el.name || i));
              });
              return out.slice(0, 30);
            }"""
            )
        for tag in unlabeled:
            issues.append(
                _issue(
                    type_="empty_form_label",
                    severity="medium",
                    page_url=url,
                    element_selector=tag[:200],
                    description="Form control may lack accessible label",
                    evidence=tag,
                )
            )
    except Exception:
        pass

    return issues
