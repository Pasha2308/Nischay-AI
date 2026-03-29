from playwright.async_api import Playwright


async def launch_browser(playwright: Playwright, requires_login: bool = False):
    print("🚀 PLAYWRIGHT LAUNCH TRIGGERED", flush=True)
    browser = await playwright.chromium.launch(
        headless=False,
        slow_mo=80,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
    )
    return browser
