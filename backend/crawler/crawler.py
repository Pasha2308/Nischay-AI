"""Site crawler — discovers pages, elements, forms, and navigation structure."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from backend.core.browser import launch_browser
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from shared.models.config import FrameworkConfig
from shared.utils.auth import perform_smart_auth
from shared.utils.browser_stealth import create_stealth_context
from shared.pipeline_emit import PipelineEmit
from shared.models.site_model import (
    APIEndpoint,
    AuthFlow,
    NetworkRequest,
    PageModel,
    SiteModel,
)

from shared.utils.url_utils import normalize_url, page_id_from_url

from .element_extractor import extract_elements
from .form_analyzer import analyze_forms
from .spa_handler import detect_spa_type, discover_spa_routes

logger = logging.getLogger(__name__)

def _normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    return normalize_url(url)


def _page_id(url: str) -> str:
    """Generate a stable page ID from the normalized URL."""
    return page_id_from_url(url)


def _is_same_origin(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def _is_valid_page_url(url: str) -> bool:
    """Filter out non-page URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    skip_extensions = (
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
        '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot',
        '.pdf', '.zip', '.tar', '.gz', '.mp3', '.mp4', '.webm',
        '.xml', '.rss', '.atom', '.json',
    )
    path_lower = parsed.path.lower()
    return not any(path_lower.endswith(ext) for ext in skip_extensions)


def _matches_patterns(url: str, patterns: list[str]) -> bool:
    return any(re.search(p, url) for p in patterns)


def _normalize_scan_task_for_crawl(scan_task: str | None) -> str:
    """Map FrameworkConfig.scan_task to crawl_site task_priority_map keys."""
    if not scan_task:
        return "full_app"
    st = scan_task.strip().lower()
    if st.startswith("custom:"):
        return "full_app"
    if st in ("auth", "auth_flow", "login_flow"):
        return "auth"
    if st in ("checkout", "checkout_flow", "cart_flow"):
        return "checkout"
    if st in ("forms", "form", "contact_flow"):
        return "forms"
    if st in ("full_app", "full", "full_app_scan"):
        return "full_app"
    if "auth" in st or "login" in st:
        return "auth"
    if "checkout" in st or "cart" in st or "payment" in st:
        return "checkout"
    if "form" in st:
        return "forms"
    return "full_app"


async def crawl_site(
    page: Page,
    base_url: str,
    scan_task: str,
    max_pages: int = 15,
    emit_event=None,
    *,
    extra_seed_urls: list[str] | None = None,
    log_action=None,
    log_bracketed=None,
):
    visited = set()
    queue = [base_url]
    if extra_seed_urls:
        for u in reversed(extra_seed_urls):
            if u and u not in queue:
                queue.insert(0, u)
    pages_data = []

    task_priority_map = {
        "auth": ["login", "signup", "register"],
        "checkout": ["cart", "checkout", "payment"],
        "forms": ["contact", "form", "submit"],
        "full_app": [],
    }

    priority_keywords = task_priority_map.get(scan_task, [])

    def priority_score(url):
        return sum(2 for kw in priority_keywords if kw in url.lower())

    while queue and len(visited) < max_pages:
        queue.sort(key=priority_score, reverse=True)

        current_url = queue.pop(0)

        if current_url in visited:
            continue

        if base_url not in current_url:
            continue

        visited.add(current_url)

        try:
            if emit_event:
                await emit_event(f"🔍 Scanning {len(visited)}/{max_pages}: {current_url}")

            try:
                if log_bracketed:

                    async def _bfs_goto() -> None:
                        await page.goto(current_url, wait_until="networkidle", timeout=15000)

                    await log_bracketed(
                        page,
                        phase="crawl",
                        action_type="navigate",
                        description="crawl_site BFS load",
                        target_url=current_url,
                        coro=_bfs_goto,
                    )
                else:
                    await page.goto(current_url, wait_until="networkidle", timeout=15000)
            except Exception as e:
                if log_action and not log_bracketed:
                    await log_action(
                        page,
                        phase="crawl",
                        action_type="navigate",
                        description="crawl_site BFS load failed",
                        target_url=current_url,
                        outcome="failed",
                        outcome_detail=str(e)[:400],
                    )
                raise

            links = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href)",
            )

            for link in links:
                if link not in visited and link not in queue:
                    if base_url in link:
                        queue.append(link)

            pages_data.append({
                "url": current_url,
                "title": await page.title(),
                "links": len(links),
            })

        except Exception as e:
            if emit_event:
                await emit_event(f"⚠️ Error: {str(e)[:60]}")
            continue

    if emit_event:
        await emit_event(f"✅ Crawl done: {len(visited)} pages")

    return pages_data


class Crawler:
    """Crawls a website using Playwright and builds a SiteModel.

    URL discovery uses :func:`crawl_site` (priority-ordered BFS on ``<a href>``
    within the site). Each discovered URL is then loaded in a fresh tab to
    extract elements, forms, and navigation edges for the pipeline.
    """

    def __init__(self, config: FrameworkConfig, output_dir: Path, ai_client=None):
        self.config = config
        self.crawl_config = config.crawl
        self.output_dir = output_dir
        self.baselines_dir = output_dir / "baselines"
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self._ai_client = ai_client

        self._pages: list[PageModel] = []
        self._nav_graph: dict[str, list[str]] = {}
        self._api_endpoints: dict[str, APIEndpoint] = {}
        self._is_spa: bool = False
        self._spa_checked: bool = False
        self._crawl_lock = asyncio.Lock()
        self._emit: PipelineEmit | None = None
        self._log_action: Any | None = None
        self._log_bracketed: Any | None = None

    async def crawl(
        self,
        browser_context: BrowserContext | None = None,
        browser: Browser | None = None,
        *,
        skip_auth: bool = False,
        post_login_url: str | None = None,
        auth_flow_override: AuthFlow | None = None,
        emit: PipelineEmit | None = None,
        log_action: Any | None = None,
        log_bracketed: Any | None = None,
    ) -> SiteModel:
        print("[CRAWL START] crawl function called", flush=True)
        print(f"[CRAWL START] url={self.crawl_config.target_url}", flush=True)
        print(f"[CRAWL START] page object=None (crawler creates pages)", flush=True)
        """Execute the crawl and return a SiteModel.

        When ``browser_context`` and ``browser`` are provided (pipeline mode), uses
        that shared session and does **not** close the browser (caller owns lifecycle).

        ``skip_auth`` + ``post_login_url`` / ``auth_flow_override`` are used when the
        orchestrator already authenticated the same context.
        """
        start_time = time.time()
        target = self.crawl_config.target_url
        logger.info("Starting crawl of %s", target)
        self._emit = emit
        self._log_action = log_action
        self._log_bracketed = log_bracketed
        if emit:
            try:
                await emit("crawler", "started", {"target_url": target})
            except Exception:
                pass

        auth_flow: AuthFlow | None = auth_flow_override
        post_login = post_login_url
        external = browser_context is not None and browser is not None

        try:
            if external:
                context = browser_context
                assert browser is not None
                if self.config.auth and not skip_auth:
                    logger.info("Authenticating before crawl (shared context)...")
                    result = await perform_smart_auth(
                        context, self.config.auth, ai_client=self._ai_client,
                    )
                    if result.success:
                        auth_flow = result.auth_flow
                        post_login = result.post_login_url
                        logger.info("Authentication successful")
                    else:
                        logger.error("Authentication failed: %s", result.error)
                elif self.config.auth and skip_auth:
                    logger.info("Using pre-authenticated shared browser context for crawl")

                await self._priority_crawl(context, target, post_login_url=post_login)

                if self.config.auth and auth_flow:
                    await self._probe_auth_requirements(browser)
                else:
                    for page_model in self._pages:
                        page_model.auth_required = False

            else:
                async with async_playwright() as playwright:
                    logger.debug(
                        "Launching Playwright browser (type=%s)...",
                        self.config.browser_type,
                    )
                    browser = await launch_browser(
                        playwright,
                        browser_type=self.config.browser_type,
                        requires_login=bool(self.config.auth),
                    )
                    logger.debug(
                        "Creating stealth browser context (viewport=%dx%d)",
                        self.crawl_config.viewport.width,
                        self.crawl_config.viewport.height,
                    )
                    context = await create_stealth_context(
                        browser,
                        viewport={
                            "width": self.crawl_config.viewport.width,
                            "height": self.crawl_config.viewport.height,
                        },
                        user_agent=self.crawl_config.user_agent,
                    )

                    auth_flow = None
                    post_login = None
                    if self.config.auth:
                        logger.info("Authenticating before crawl...")
                        result = await perform_smart_auth(
                            context, self.config.auth, ai_client=self._ai_client,
                        )
                        if result.success:
                            auth_flow = result.auth_flow
                            post_login = result.post_login_url
                            logger.info("Authentication successful")
                        else:
                            logger.error("Authentication failed: %s", result.error)

                    await self._priority_crawl(context, target, post_login_url=post_login)

                    if self.config.auth and auth_flow:
                        await self._probe_auth_requirements(browser)
                    else:
                        for page_model in self._pages:
                            page_model.auth_required = False

                    await browser.close()
        finally:
            self._emit = None
            self._log_action = None
            self._log_bracketed = None

        duration = time.time() - start_time
        logger.info(
            "Crawl complete: %d pages discovered in %.1fs",
            len(self._pages), duration,
        )
        if emit:
            try:
                payload: dict[str, Any] = {
                    "pages": len(self._pages),
                    "duration_seconds": round(duration, 2),
                }
                await emit("crawler", "finished", payload)
            except Exception:
                pass

        return SiteModel(
            base_url=target,
            pages=self._pages,
            navigation_graph=self._nav_graph,
            api_endpoints=list(self._api_endpoints.values()),
            auth_flow=auth_flow,
            crawl_metadata={
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_seconds": round(duration, 2),
                "pages_found": len(self._pages),
                "is_spa": self._is_spa,
            },
        )

    async def _probe_auth_requirements(self, browser) -> None:
        """Probe each discovered page in a clean context to determine if auth is required."""
        if not self._pages:
            return
        logger.info("Probing %d pages for auth requirements", len(self._pages))
        clean_context = await browser.new_context(
            viewport={
                "width": self.crawl_config.viewport.width,
                "height": self.crawl_config.viewport.height,
            },
            user_agent=self.crawl_config.user_agent,
        )
        probe_page = await clean_context.new_page()

        login_path = ""
        if self.config.auth and self.config.auth.login_url:
            login_path = urlparse(self.config.auth.login_url).path.rstrip("/")

        for idx, page_model in enumerate(self._pages):
            logger.debug("Auth probing [%d/%d]: %s", idx + 1, len(self._pages), page_model.url)
            try:
                _lb = getattr(self, "_log_bracketed", None)
                if _lb:
                    _probe_url = page_model.url

                    async def _probe_goto():
                        return await probe_page.goto(
                            _probe_url,
                            wait_until="domcontentloaded",
                            timeout=10000,
                        )

                    resp = await _lb(
                        probe_page,
                        phase="crawl",
                        action_type="navigate",
                        description=f"auth probe page [{idx + 1}/{len(self._pages)}]",
                        target_url=page_model.url,
                        coro=_probe_goto,
                    )
                else:
                    resp = await probe_page.goto(
                        page_model.url,
                        wait_until="domcontentloaded",
                        timeout=10000,
                    )
                if resp is None:
                    page_model.auth_required = True
                    continue

                status = resp.status
                final_url = probe_page.url

                # HTTP 401/403 → requires auth
                if status in (401, 403):
                    page_model.auth_required = True
                # Redirected to login URL
                elif login_path and login_path in urlparse(final_url).path:
                    page_model.auth_required = True
                else:
                    # Check if landing page looks like a login form
                    title = (await probe_page.title() or "").lower()
                    if any(kw in title for kw in ("login", "sign in", "log in", "authenticate")):
                        page_model.auth_required = True
                    else:
                        page_model.auth_required = False

            except Exception as e:
                logger.debug("Auth probe failed for %s: %s", page_model.url, e)
                page_model.auth_required = None

        await probe_page.close()
        await clean_context.close()
        auth_count = sum(1 for p in self._pages if p.auth_required is True)
        public_count = sum(1 for p in self._pages if p.auth_required is False)
        logger.info("Auth probe: %d require auth, %d public", auth_count, public_count)

    # ------------------------------------------------------------------
    # Core crawl loop
    # ------------------------------------------------------------------

    async def _load_and_process_page(
        self,
        context: BrowserContext,
        url: str,
        start_url: str,
    ) -> tuple[PageModel | None, set[str]]:
        """Load one URL in its own tab; returns model and discovered links."""
        page = await context.new_page()
        network_requests: list[NetworkRequest] = []
        self._attach_network_listener(page, network_requests)
        delay_ms = getattr(self.crawl_config, "inter_page_delay_ms", 0) or 0
        if delay_ms > 0:
            await page.wait_for_timeout(min(delay_ms, 5000))

        try:
            loaded = await self._navigate_with_retry(page, url)
            if not loaded:
                logger.warning("Failed to load: %s", url)
                return None, set()

            async with self._crawl_lock:
                if not self._spa_checked:
                    spa_type = await detect_spa_type(page)
                    self._is_spa = spa_type != "traditional"
                    self._spa_checked = True
                    if self._is_spa:
                        logger.info("SPA detected (routing: %s)", spa_type)

            logger.debug("Extracting page content: elements, forms...")
            page_model = await self._process_page(page, url, network_requests)
            discovered = await self._discover_all_links(page, url)
            logger.info(
                "Page '%s' — %d links discovered",
                page_model.title or url,
                len(discovered),
            )
            return page_model, discovered
        except Exception as e:
            logger.error("Error enriching %s: %s", url, e)
            return None, set()
        finally:
            await page.close()

    async def _priority_crawl(
        self, context: BrowserContext, start_url: str,
        post_login_url: str | None = None,
    ) -> None:
        """Discover URLs with :func:`crawl_site`, then enrich each with PageModel data."""
        self._pages.clear()
        self._nav_graph.clear()
        self._api_endpoints.clear()
        self._is_spa = False
        self._spa_checked = False

        extra_seed: list[str] = []
        if post_login_url and _normalize_url(post_login_url) != _normalize_url(start_url):
            logger.info("Seeding post-login URL into crawl queue: %s", post_login_url)
            if self._url_in_scope(post_login_url):
                extra_seed.append(post_login_url)

        scan_task = _normalize_scan_task_for_crawl(getattr(self.config, "scan_task", None))

        async def emit_line(msg: str) -> None:
            emit = self._emit
            if emit:
                try:
                    await emit("crawler", "log", {"message": msg})
                except Exception:
                    pass

        page = await context.new_page()
        try:
            pages_data = await crawl_site(
                page,
                start_url,
                scan_task,
                max_pages=self.crawl_config.max_pages,
                emit_event=emit_line,
                extra_seed_urls=extra_seed or None,
                log_action=self._log_action,
                log_bracketed=self._log_bracketed,
            )
        finally:
            await page.close()

        total = len(pages_data)
        for i, pd in enumerate(pages_data):
            url = pd["url"]
            if not self._url_in_scope(url):
                logger.debug("Skipping out-of-scope URL from crawl: %s", url)
                continue
            logger.info("Enriching [%d/%d]: %s", i + 1, total, url)
            page_model, discovered = await self._load_and_process_page(
                context, url, start_url,
            )
            if page_model is None:
                continue
            self._pages.append(page_model)
            pid = page_model.page_id
            self._nav_graph[pid] = []
            for link_url in discovered:
                if not _is_valid_page_url(link_url):
                    continue
                if not _is_same_origin(self.crawl_config.target_url, link_url):
                    continue
                if not self._url_in_scope(link_url):
                    continue
                link_id = _page_id(link_url)
                self._nav_graph[pid].append(link_id)

        logger.info("Crawl finished: %d pages enriched", len(self._pages))

    def _url_in_scope(self, url: str) -> bool:
        if not _is_same_origin(self.crawl_config.target_url, url):
            return False
        if self.crawl_config.exclude_patterns and _matches_patterns(
            url, self.crawl_config.exclude_patterns
        ):
            return False
        if self.crawl_config.include_patterns and not _matches_patterns(
            url, self.crawl_config.include_patterns
        ):
            return False
        return True

    # ------------------------------------------------------------------
    # Page processing
    # ------------------------------------------------------------------

    async def _process_page(
        self, page: Page, url: str, network_requests: list[NetworkRequest]
    ) -> PageModel:
        """Extract all information from a loaded page."""
        title = ""
        try:
            title = await page.title() or ""
        except Exception:
            pass

        logger.debug("Classifying page type...")
        page_type = await self._classify_page(page)
        logger.debug("Page type: %s", page_type)
        logger.debug("Extracting interactive elements...")
        elements = await extract_elements(page)
        logger.debug("Found %d elements (%d interactive)",
                     len(elements), sum(1 for e in elements if e.is_interactive))
        logger.debug("Analyzing forms...")
        forms = await analyze_forms(page)
        logger.debug("Found %d forms", len(forms))

        pid = _page_id(url)
        screenshot_path = ""
        if self.crawl_config.capture_page_screenshots:
            try:
                logger.debug("Capturing screenshot for %s...", url)
                screenshot_path = str(self.baselines_dir / f"{pid}_screenshot.png")
                await page.screenshot(path=screenshot_path, full_page=True)
            except Exception as e:
                logger.debug("Screenshot failed for %s: %s", url, e)
                screenshot_path = ""

        dom_path = ""
        if self.crawl_config.save_dom_snapshot:
            try:
                logger.debug("Capturing DOM snapshot for %s...", url)
                dom_path = str(self.baselines_dir / f"{pid}_dom.html")
                dom_content = await page.content()
                with open(dom_path, "w", encoding="utf-8") as f:
                    f.write(dom_content)
            except Exception as e:
                logger.debug("DOM snapshot failed for %s: %s", url, e)
                dom_path = ""

        return PageModel(
            page_id=pid,
            url=url,
            page_type=page_type,
            title=title,
            elements=elements,
            forms=forms,
            network_requests=list(network_requests),
            screenshot_path=screenshot_path,
            dom_snapshot_path=dom_path,
        )

    # ------------------------------------------------------------------
    # Link discovery (multiple strategies)
    # ------------------------------------------------------------------

    async def _discover_all_links(self, page: Page, base_url: str) -> set[str]:
        """Run all link discovery strategies and return the union of results."""
        discovered = set()

        # 1. Static DOM links (<a>, <area>, <frame>, <iframe>)
        logger.debug("  Link discovery: extracting static links...")
        static = await self._extract_static_links(page, base_url)
        discovered.update(static)
        logger.debug("  Link discovery: %d static links found", len(static))

        # 2. SPA route links
        if self._is_spa:
            try:
                logger.debug("  Link discovery: discovering SPA routes...")
                spa = await discover_spa_routes(page, base_url)
                discovered.update(spa)
                logger.debug("  Link discovery: %d SPA routes found", len(spa))
            except Exception as e:
                logger.debug("SPA route discovery error: %s", e)

        # 3. Dynamic links (onclick, data attributes, meta refresh)
        logger.debug("  Link discovery: extracting dynamic links...")
        dynamic = await self._extract_dynamic_links(page, base_url)
        discovered.update(dynamic)
        logger.debug("  Link discovery: %d dynamic links found", len(dynamic))

        # 4. Interactive links (click menus/dropdowns to reveal hidden nav)
        logger.debug("  Link discovery: clicking nav menus/dropdowns...")
        interactive = await self._discover_interactive_links(page, base_url)
        discovered.update(interactive)
        logger.debug("  Link discovery: %d interactive links found", len(interactive))

        logger.debug(
            "Link discovery for %s: %d static, %d dynamic, %d interactive, %d total unique",
            base_url, len(static), len(dynamic), len(interactive), len(discovered),
        )
        return discovered

    async def _extract_static_links(self, page: Page, base_url: str) -> set[str]:
        """Extract links from <a href>, <area href>, frame/iframe src."""
        try:
            hrefs = await page.evaluate("""() => {
                const results = [];

                // Standard anchor links
                document.querySelectorAll('a[href]').forEach(el => {
                    results.push(el.href);
                });

                // Image map area links
                document.querySelectorAll('area[href]').forEach(el => {
                    results.push(el.href);
                });

                // Frames / iframes
                document.querySelectorAll('frame[src], iframe[src]').forEach(el => {
                    if (el.src) results.push(el.src);
                });

                return results.filter(h =>
                    h &&
                    !h.startsWith('javascript:') &&
                    !h.startsWith('mailto:') &&
                    !h.startsWith('tel:') &&
                    !h.startsWith('data:') &&
                    !h.startsWith('blob:')
                );
            }""")
            return self._resolve_urls(hrefs, base_url)
        except Exception as e:
            logger.debug("Static link extraction failed: %s", e)
            return set()

    async def _extract_dynamic_links(self, page: Page, base_url: str) -> set[str]:
        """Extract URLs from onclick, data attributes, formaction, meta refresh."""
        try:
            urls = await page.evaluate("""() => {
                const results = [];

                // onclick handlers — extract URL patterns
                document.querySelectorAll('[onclick]').forEach(el => {
                    const onclick = el.getAttribute('onclick') || '';
                    const locMatch = onclick.match(
                        /(?:window\\.)?location(?:\\.href)?\\s*=\\s*["']([^"']+)["']/
                    );
                    if (locMatch) results.push(locMatch[1]);
                    const navMatch = onclick.match(
                        /(?:navigate|goto|redirect|router\\.push)\\s*\\(?\\s*["']([^"']+)["']/i
                    );
                    if (navMatch) results.push(navMatch[1]);
                });

                // data-href, data-url, data-link, data-to, data-route
                const dataAttrs = ['data-href', 'data-url', 'data-link', 'data-to', 'data-route'];
                for (const attr of dataAttrs) {
                    document.querySelectorAll(`[${attr}]`).forEach(el => {
                        const val = el.getAttribute(attr);
                        if (val && (val.startsWith('/') || val.startsWith('http'))) {
                            results.push(val);
                        }
                    });
                }

                // Buttons with formaction
                document.querySelectorAll('button[formaction], input[formaction]').forEach(el => {
                    const val = el.getAttribute('formaction');
                    if (val) results.push(val);
                });

                // Meta refresh
                document.querySelectorAll('meta[http-equiv="refresh"]').forEach(el => {
                    const content = el.getAttribute('content') || '';
                    const match = content.match(/url\\s*=\\s*["']?([^"';\\s]+)/i);
                    if (match) results.push(match[1]);
                });

                // Form actions
                document.querySelectorAll('form[action]').forEach(el => {
                    const action = el.getAttribute('action');
                    if (action && action !== '#' && !action.startsWith('javascript:')) {
                        results.push(action);
                    }
                });

                return results.filter(r => r && !r.startsWith('javascript:'));
            }""")
            return self._resolve_urls(urls, base_url)
        except Exception as e:
            logger.debug("Dynamic link extraction failed: %s", e)
            return set()

    async def _discover_interactive_links(self, page: Page, base_url: str) -> set[str]:
        """Click nav menus, dropdowns, hamburger buttons to reveal hidden links."""
        discovered = set()

        try:
            # Collect all currently-visible links BEFORE interaction
            links_before = await self._get_visible_link_hrefs(page)

            # Find navigation toggle elements
            toggles = await page.evaluate("""() => {
                const selectors = [];
                const candidates = document.querySelectorAll(
                    'nav button, nav [role="button"], ' +
                    '[class*="menu-toggle"], [class*="hamburger"], [class*="nav-toggle"], ' +
                    '[class*="dropdown-toggle"], [aria-haspopup="true"], ' +
                    '[data-toggle="dropdown"], [data-bs-toggle="dropdown"], ' +
                    'button[aria-expanded="false"], [class*="navbar-toggler"], ' +
                    'details > summary'
                );
                for (const el of candidates) {
                    if (el.offsetParent === null && !el.closest('details')) continue;
                    let sel = '';
                    if (el.id) sel = '#' + CSS.escape(el.id);
                    else if (el.getAttribute('aria-label'))
                        sel = `[aria-label="${el.getAttribute('aria-label')}"]`;
                    else if (el.className && typeof el.className === 'string') {
                        const cls = el.className.trim().split(/\\s+/)[0];
                        if (cls) sel = el.tagName.toLowerCase() + '.' + CSS.escape(cls);
                    }
                    if (sel) selectors.push(sel);
                }
                return selectors.slice(0, 8);
            }""")

            original_url = page.url

            _lb = getattr(self, "_log_bracketed", None)
            _la = getattr(self, "_log_action", None)
            for selector in toggles:
                try:
                    el = await page.query_selector(selector)
                    if not el or not await el.is_visible():
                        continue

                    if _lb:
                        _h = el

                        async def _menu_click() -> None:
                            await _h.click(timeout=3000)
                            await page.wait_for_timeout(500)

                        await _lb(
                            page,
                            phase="crawl",
                            action_type="click",
                            description="Interactive link discovery — menu/toggle",
                            target_element=selector,
                            coro=_menu_click,
                        )
                    else:
                        await el.click(timeout=3000)
                        await page.wait_for_timeout(500)

                    # Collect links AFTER clicking
                    links_after = await self._get_visible_link_hrefs(page)
                    new_links = links_after - links_before
                    discovered.update(self._resolve_urls(list(new_links), base_url))

                    # Close menu
                    try:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

                except Exception as e:
                    logger.debug("Interactive click failed (%s): %s", selector, e)

            # Restore original page if we navigated away
            if page.url != original_url:
                try:
                    if _lb:

                        async def _restore_orig() -> None:
                            await page.goto(
                                original_url,
                                wait_until="domcontentloaded",
                                timeout=15000,
                            )

                        await _lb(
                            page,
                            phase="crawl",
                            action_type="navigate",
                            description="Restore URL after interactive link discovery",
                            target_url=original_url,
                            coro=_restore_orig,
                        )
                    else:
                        await page.goto(
                            original_url,
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                except Exception:
                    pass

        except Exception as e:
            logger.debug("Interactive link discovery error: %s", e)

        return discovered

    async def _get_visible_link_hrefs(self, page: Page) -> set[str]:
        """Get hrefs of all currently visible links on the page."""
        try:
            hrefs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const rect = a.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    })
                    .map(a => a.href)
                    .filter(h =>
                        h && !h.startsWith('javascript:') &&
                        !h.startsWith('mailto:') && !h.startsWith('tel:')
                    );
            }""")
            return set(hrefs)
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def _navigate_with_retry(self, page: Page, url: str, retries: int = 1) -> bool:
        """Navigate to a URL with retry on failure (tuned for faster crawls)."""
        for attempt in range(retries + 1):
            try:
                logger.debug("Navigating to %s (attempt %d/%d)...", url, attempt + 1, retries + 1)
                lb = getattr(self, "_log_bracketed", None)
                if lb:

                    async def _do_nav() -> None:
                        resp = await page.goto(
                            url, wait_until="domcontentloaded", timeout=20000
                        )
                        if resp is None:
                            logger.warning("Navigation returned no response for %s", url)
                            raise RuntimeError("no navigation response")
                        if resp and resp.status >= 400 and resp.status != 404:
                            logger.warning("HTTP %d for %s", resp.status, url)
                        if self.crawl_config.wait_for_idle:
                            logger.debug("Waiting for network idle...")
                            try:
                                await page.wait_for_load_state("networkidle", timeout=5000)
                            except Exception:
                                logger.debug(
                                    "Network idle timeout, short fallback wait",
                                )
                                await page.wait_for_timeout(500)

                    await lb(
                        page,
                        phase="crawl",
                        action_type="navigate",
                        description=f"enrich page load (attempt {attempt + 1})",
                        target_url=url,
                        coro=_do_nav,
                    )
                    return True

                print(f"[GOTO] about to navigate to {url}", flush=True)
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if resp is None:
                    logger.warning("Navigation returned no response for %s", url)
                    raise RuntimeError("no navigation response")
                if resp and resp.status >= 400 and resp.status != 404:
                    logger.warning("HTTP %d for %s", resp.status, url)

                if self.crawl_config.wait_for_idle:
                    logger.debug("Waiting for network idle...")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        logger.debug("Network idle timeout, short fallback wait")
                        await page.wait_for_timeout(500)

                return True
            except PlaywrightTimeoutError as e:
                la = getattr(self, "_log_action", None)
                if la and not getattr(self, "_log_bracketed", None):
                    await la(
                        page,
                        phase="crawl",
                        action_type="navigate",
                        description="enrich page load timeout",
                        target_url=url,
                        outcome="failed",
                        outcome_detail=str(e)[:400],
                    )
                if attempt < retries:
                    logger.debug("Navigation timeout retry %d for %s: %s", attempt + 1, url, e)
                    await asyncio.sleep(0.5)
                else:
                    logger.warning("Navigation timeout after %d retries: %s — %s", retries, url, e)
                    return False
            except Exception as e:
                la = getattr(self, "_log_action", None)
                if la and not getattr(self, "_log_bracketed", None):
                    await la(
                        page,
                        phase="crawl",
                        action_type="navigate",
                        description="enrich page load error",
                        target_url=url,
                        outcome="failed",
                        outcome_detail=str(e)[:400],
                    )
                if attempt < retries:
                    logger.debug("Retry %d for %s: %s", attempt + 1, url, e)
                    await asyncio.sleep(0.5)
                else:
                    logger.warning("Navigation failed after %d retries: %s — %s", retries, url, e)
                    return False
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_urls(self, hrefs: list[str], base_url: str) -> set[str]:
        """Resolve a list of hrefs to absolute, deduplicated, valid URLs."""
        resolved = set()
        for href in hrefs:
            try:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    clean += f"?{parsed.query}"
                if _is_valid_page_url(clean):
                    resolved.add(clean)
            except Exception:
                pass
        return resolved

    def _attach_network_listener(
        self, page: Page, nr_list: list[NetworkRequest]
    ) -> None:
        """Attach a network response listener to a page."""
        async def on_response(response):
            try:
                req = response.request
                nr_list.append(NetworkRequest(
                    url=req.url,
                    method=req.method,
                    resource_type=req.resource_type,
                    status=response.status,
                    content_type=response.headers.get("content-type", ""),
                ))
                if req.resource_type in ("xhr", "fetch"):
                    key = f"{req.method}:{urlparse(req.url).path}"
                    if key not in self._api_endpoints:
                        self._api_endpoints[key] = APIEndpoint(
                            url=req.url,
                            method=req.method,
                            response_content_type=response.headers.get("content-type"),
                            status_codes_seen=[response.status],
                        )
                    else:
                        ep = self._api_endpoints[key]
                        if response.status not in ep.status_codes_seen:
                            ep.status_codes_seen.append(response.status)
            except Exception:
                pass

        page.on("response", on_response)

    async def _classify_page(self, page: Page) -> str:
        """Classify a page based on its content and structure."""
        try:
            return await page.evaluate("""() => {
                const forms = document.querySelectorAll('form');
                const inputs = document.querySelectorAll('input, textarea, select');
                const dashWidgets = document.querySelectorAll(
                    '[class*="dashboard"], [class*="widget"], [class*="chart"], [class*="metric"]'
                );
                const errorInd = document.querySelectorAll(
                    '[class*="error"], [class*="404"], [class*="not-found"]'
                );
                const title = document.title.toLowerCase();
                const h1 = (document.querySelector('h1')?.textContent || '').toLowerCase();

                if (errorInd.length > 0 || title.includes('404') || title.includes('error') ||
                    h1.includes('not found') || h1.includes('page not found'))
                    return 'error';
                if (forms.length > 0 && inputs.length >= 3)
                    return 'form';
                if (dashWidgets.length > 0)
                    return 'dashboard';
                if (document.querySelectorAll('table, [role="grid"]').length > 0 &&
                    document.querySelectorAll('a').length > 10)
                    return 'listing';
                if (document.querySelector(
                    'article, [class*="detail"], [class*="product"], [itemtype*="schema.org"]'
                ))
                    return 'detail';
                return 'static';
            }""")
        except Exception:
            return "static"
