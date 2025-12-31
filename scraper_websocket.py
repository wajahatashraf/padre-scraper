import asyncio
import random
import json
import websockets
import msgpack
from datetime import datetime
from pprint import pprint
from playwright.async_api import async_playwright, Page
import config  # GOOGLE_EMAIL, GOOGLE_PASSWORD, SECONDARY_PASSWORD

# ================== CONFIG ==================
URL = "https://trade.padre.gg/sign-in?backToUrl=%2Ftracker"
GOOGLE_EMAIL = config.GOOGLE_EMAIL
GOOGLE_PASSWORD = config.GOOGLE_PASSWORD
SECONDARY_PASSWORD = config.SECONDARY_PASSWORD

USER_AGENT = random.choice([
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36"
])

# ================== WEBSOCKET SERVER ==================
connected_clients = set()

async def websocket_server():
    async def handler(websocket):  # websockets>=11 requires only 'websocket' argument
        print(f"🤖 Client connected: {websocket.remote_address}")
        connected_clients.add(websocket)
        try:
            async for msg in websocket:
                print(f"📨 Received from client: {msg}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"❌ Connection closed: {e}")
        except Exception as e:
            print(f"⚠️ Handler error: {e}")
        finally:
            connected_clients.remove(websocket)
            print(f"🛑 Client disconnected: {websocket.remote_address}")

    server = await websockets.serve(handler, "127.0.0.1", 8765)
    print("🚀 WebSocket relay server running on ws://127.0.0.1:8765")
    return server

async def relay_to_clients(data):
    if not connected_clients:
        return
    message = json.dumps(data)
    to_remove = []

    for client in connected_clients:
        try:
            await client.send(message)
        except Exception as e:
            print(f"⚠️ Error sending to client {client}: {e}")
            to_remove.append(client)

    for c in to_remove:
        connected_clients.discard(c)


async def wait_for_navigation(page: Page):
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass

# ================== WEBSOCKET HANDLER ==================
def decode_msgpack(binary: bytes):
    try:
        return msgpack.unpackb(binary, raw=False)
    except:
        return None

def handle_ws(ws):
    ws.on("framereceived", lambda frame: handle_frame(frame))

def handle_frame(frame_bytes):
    if not isinstance(frame_bytes, bytes):
        return

    # -------- received time (websocket receive time) --------
    received_dt = datetime.now()
    received_time = received_dt.strftime("%A, %b %d, %Y %H:%M:%S.%f")[:-3]

    decoded = decode_msgpack(frame_bytes)
    if not decoded:
        return

    if not (
        isinstance(decoded, list)
        and len(decoded) > 1
        and decoded[0] == 5
        and decoded[1] == 13
    ):
        return

    # Attach receive time WITHOUT modifying server data
    meta = {
        "ws_received_time": received_time,
        "ws_received_ts_ms": int(received_dt.timestamp() * 1000),
    }

    asyncio.create_task(relay_to_clients({
        "meta": meta,
        "data": decoded
    }))

    print("\n📨 DECODED MESSAGE (RAW):")
    print(f"🕒 WS RECEIVED TIME: {received_time}")
    pprint(decoded)
    print("=" * 80)

# ================== LOGIN HELPERS ==================
async def type_human(element, text: str):
    for char in text:
        await element.type(char, delay=random.randint(50, 150))
    await asyncio.sleep(random.uniform(0.5, 1.5))

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

# ================== MAIN ==================
async def main():
    # Start WebSocket relay server
    server = await websocket_server()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--headless=new",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-infobars",
                "--disable-extensions",
                "--start-maximized",
                "--window-size=1280,720",
                "--disable-notifications",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--deterministic-fetch",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            user_agent=USER_AGENT
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
        print("📡 Listening to Padre.gg WebSocket traffic...")

        await page.reload()
        await asyncio.Future()  # keep script running

asyncio.run(main())
