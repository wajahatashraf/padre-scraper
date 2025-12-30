import asyncio
import random
import json
from playwright.async_api import async_playwright, Page
import msgpack
import config
# ================== CONFIG ==================
URL = "https://trade.padre.gg/sign-in?backToUrl=%2Ftracker"
GOOGLE_EMAIL = config.GOOGLE_EMAIL
GOOGLE_PASSWORD = config.GOOGLE_PASSWORD
SECONDARY_PASSWORD = config.SECONDARY_PASSWORD
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ================== HELPER FUNCTIONS ==================
async def wait_for_navigation(page: Page):
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass


async def type_human(element, text: str):
    for char in text:
        await element.type(char, delay=random.randint(50, 150))
    await asyncio.sleep(random.uniform(0.5, 1.5))


def decode_msgpack(binary: bytes):
    try:
        return msgpack.unpackb(binary, raw=False)
    except:
        return None


def handle_frame(frame_bytes):
    if isinstance(frame_bytes, bytes):
        decoded = decode_msgpack(frame_bytes)
        if decoded:
            # Only print/process specific messages
            if isinstance(decoded, list) and len(decoded) > 1 and decoded[0] == 5 and decoded[1] == 13:
                # Print as JSON string so Flask can parse it
                print(json.dumps(decoded, ensure_ascii=False))
                # Flush to ensure immediate output
                import sys
                sys.stdout.flush()


# ================== GOOGLE LOGIN ==================
async def submit_google_credentials(popup, email, password):
    try:
        email_input = await popup.wait_for_selector("//input[@type='email' or @name='identifier']", timeout=15000)
        await type_human(email_input, email)
        await email_input.press("Enter")
        await asyncio.sleep(random.uniform(3, 5))
        await popup.screenshot(path="email_entered.png")
        print("📸 Screenshot saved: email_entered.png")
    except:
        print("⚠️ Email input not found")

    try:
        password_input = await popup.wait_for_selector("//input[@type='password']", timeout=15000)
        await type_human(password_input, password)
        await password_input.press("Enter")
        await asyncio.sleep(random.uniform(5, 7))
        await popup.screenshot(path="password_entered.png")
        print("📸 Screenshot saved: password_entered.png")
    except:
        print("⚠️ Password input not found")


async def handle_secondary_login(page, password):
    try:
        await page.reload()
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="page_after_reload.png")
        print("📸 Screenshot saved: page_after_reload.png")

        secondary_input = await page.wait_for_selector("//input[@placeholder='Password']", timeout=15000)
        await type_human(secondary_input, password)
        login_btn = await page.wait_for_selector("//button[@type='submit' and contains(.,'Login')]", timeout=15000)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await login_btn.click()
        await asyncio.sleep(5)
        await page.screenshot(path="secondary_logged_in.png")
        print("📸 Screenshot saved: secondary_logged_in.png")
    except:
        print("⚠️ Secondary password step not found")


async def check_retry(page):
    try:
        retry_btn = await page.query_selector("//button[contains(.,'Try again')]")
        if retry_btn:
            await retry_btn.click()
            print("🔄 Clicked 'Try again' button")
            await asyncio.sleep(2)
            await page.screenshot(path="retry_clicked.png")
            print("📸 Screenshot saved: retry_clicked.png")
    except:
        pass


def handle_ws(ws):
    ws.on("framereceived", lambda frame: handle_frame(frame))


# ================== MAIN SCRIPT ==================
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            args=[
                "--headless=new",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
                "--start-maximized",
            ],
        )

        context = await browser.new_context(
            viewport=None,
            locale="en-US",
            user_agent=USER_AGENT,
        )
        page = await context.new_page()

        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        await page.goto(URL)
        print("🌍 Opened Padre.gg")
        await page.screenshot(path="homepage.png")

        google_btn = await page.wait_for_selector("//button[@data-testid='gmail-login-button']", timeout=30000)
        await google_btn.scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await google_btn.click()
        print("✅ Google login button clicked")

        popup = await context.wait_for_event("page")
        await popup.wait_for_load_state()
        await popup.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await popup.screenshot(path="google_popup.png")
        print("📸 Screenshot saved: google_popup.png")

        await submit_google_credentials(popup, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        await page.bring_to_front()
        await wait_for_navigation(page)
        await check_retry(page)
        await handle_secondary_login(page, SECONDARY_PASSWORD)

        page.on("websocket", lambda ws: handle_ws(ws))
        print("📡 Listening for WebSocket frames...")
        await page.reload()

        # Keep running
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())