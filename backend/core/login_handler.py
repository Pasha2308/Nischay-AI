import asyncio
from playwright.async_api import Page

async def handle_login(page: Page, credentials: dict, emit_event) -> bool:
    """
    Login strategy:
    1. Try programmatic login
    2. If fails → human login
    3. Detect success
    4. Timeout 180s
    """

    requires_login = credentials.get("username") or credentials.get("login_url")
    if not requires_login:
        return True

    login_url = credentials.get("login_url") or await _find_login_url(page)

    await emit_event("🔐 Navigating to login page...")
    try:
        await page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)
    except Exception as e:
        await emit_event(f"⚠️ Could not load login page: {str(e)[:60]}")
        return False

    programmatic_success = False

    if credentials.get("username") and credentials.get("password"):
        await emit_event("⚡ Attempting programmatic login...")
        programmatic_success = await _try_programmatic_login(page, credentials, emit_event)

    if programmatic_success:
        await emit_event("✅ Login successful — starting scan")
        return True

    await emit_event("⚠️ Programmatic login failed — browser window is open")
    await emit_event("👤 Please log in manually in the browser window")
    await emit_event("⏳ Waiting up to 3 minutes for login...")

    return await _wait_for_human_login(page, emit_event, 180)


async def _try_programmatic_login(page: Page, credentials: dict, emit_event) -> bool:
    try:
        username = credentials["username"]
        password = credentials["password"]

        user = await page.query_selector("input[type='email'], input[type='text']")
        pwd = await page.query_selector("input[type='password']")

        if not user or not pwd:
            return False

        await user.fill(username)
        await pwd.fill(password)

        btn = await page.query_selector("button[type='submit'], input[type='submit']")
        if not btn:
            return False

        old_url = page.url
        await btn.click()

        await page.wait_for_timeout(3000)

        if page.url != old_url:
            return True

        still_pwd = await page.query_selector("input[type='password']")
        return not still_pwd

    except Exception:
        return False


async def _human_login_success_indicators(page: Page, start_url: str) -> bool:
    if page.url != start_url:
        return True

    pwd = await page.query_selector("input[type='password']")
    if not pwd:
        return True

    context = page.context
    cookies = await context.cookies()
    if len(cookies) > 0:
        return True

    nav_link = await page.query_selector(
        "a:has-text('Logout'), a:has-text('Account')"
    )
    if nav_link:
        return True

    return False


async def _wait_for_human_login(page, emit_event, timeout_seconds: int = 180):
    initial_url = page.url
    initial_cookies = await page.context.cookies()
    initial_cookie_count = len(initial_cookies)
    start_time = asyncio.get_event_loop().time()

    await emit_event("⏳ Waiting for you to log in...")

    for elapsed in range(timeout_seconds):
        await asyncio.sleep(1)

        elapsed_actual = asyncio.get_event_loop().time() - start_time

        try:
            current_url = page.url
            pwd_field = await page.query_selector("input[type='password']")
            current_cookies = await page.context.cookies()

            url_changed = current_url != initial_url
            pwd_gone = pwd_field is None
            cookies_grew = len(current_cookies) > initial_cookie_count + 2

            if elapsed_actual >= 5:
                signals = sum([url_changed, pwd_gone, cookies_grew])
                if signals >= 2:
                    await emit_event("✅ Login confirmed — resuming scan")
                    return True

        except:
            if elapsed_actual >= 5:
                await emit_event("✅ Login detected — resuming scan")
                return True

        if elapsed > 0 and elapsed % 30 == 0:
            await emit_event(f"⏳ Waiting... {timeout_seconds - elapsed}s left")

    await emit_event("❌ Login timeout — continuing without login")
    return False


async def _find_login_url(page: Page):
    try:
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href).filter(h => /login|signin|account/i.test(h))"
        )
        if links:
            return links[0]
    except:
        pass

    return page.url
