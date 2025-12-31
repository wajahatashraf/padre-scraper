import asyncio
import random
from playwright.async_api import async_playwright, Page
import msgpack
from datetime import datetime
import config

# ================== CONFIG ==================
URL = "https://trade.padre.gg/sign-in?backToUrl=%2Ftracker"
GOOGLE_EMAIL = config.GOOGLE_EMAIL
GOOGLE_PASSWORD = config.GOOGLE_PASSWORD
SECONDARY_PASSWORD = config.SECONDARY_PASSWORD

# Generate a recent desktop user-agent
recent_desktop_uas = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)  Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)  Safari/537.36"
]
USER_AGENT = random.choice(recent_desktop_uas)

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

def handle_ws(ws):
    ws.on("framereceived", lambda frame: handle_frame(frame))

def decode_msgpack(binary: bytes):
    try:
        return msgpack.unpackb(binary, raw=False)
    except:
        return None

from datetime import datetime
from pprint import pprint

def handle_frame(frame_bytes):
    if not isinstance(frame_bytes, bytes):
        return

    decoded = decode_msgpack(frame_bytes)
    if not decoded:
        return

    if not (isinstance(decoded, list) and len(decoded) > 1 and decoded[0] == 5 and decoded[1] == 13):
        return

    # ------------------------------------------------------------------
    # 🔍 SHOW RAW / NEW DATA (this is what you were missing)
    # ------------------------------------------------------------------
    print("\n📨 DECODED MESSAGE (RAW):")
    pprint(decoded)
    print("=" * 80)

    payload = decoded[2] or {}

    if payload.get("type") == "snapshot":
        items = payload.get("snapshot", {}).get("items", [])

    elif payload.get("type") == "update":
        items = payload.get("update", {}).get("updates", [])

    else:
        items = []

    for item in items:
        try:
            tweet = item.get("tweet", {}) or {}
            author = tweet.get("author", {}) or {}
            profile = author.get("profile", {}) or {}
            metrics = tweet.get("metrics", {}) or {}
            body = tweet.get("body", {}) or {}

            tweet_id = tweet.get("id")
            if not tweet_id:
                continue

            # -------- handle subtweet --------
            subtweet = tweet.get("subtweet")
            subtweet_content = None
            subtweet_author = None

            if subtweet:
                subtweet_author_data = subtweet.get("author", {}) or {}
                subtweet_profile = subtweet_author_data.get("profile", {}) or {}

                subtweet_author = {
                    "name": subtweet_profile.get("name", "Unknown"),
                    "username": subtweet_author_data.get("handle", "unknown"),
                    "id": subtweet_author_data.get("id"),
                }

                subtweet_content = subtweet.get("body", {}).get("text", "")

            # -------- handle reply target --------
            reply = tweet.get("reply")
            replying_to = None

            if reply:
                replying_to = {
                    "name": f"@{reply.get('handle')}",
                    "username": reply.get("handle"),
                    "id": reply.get("id"),
                }
            elif subtweet_author and tweet.get("type") == "REPLY":
                replying_to = subtweet_author

            # -------- timestamp formatting --------
            timestamp_ms = tweet.get("created_at", 0) or item.get("itemCreatedAt", 0)

            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            formatted_time = dt.strftime("%I:%M:%S.%f %p · %b %d, %Y")[:-3].lstrip("0")

            # -------- received time (websocket receive time) --------
            received_dt = datetime.now()
            received_time = received_dt.strftime("%A, %b %d, %Y %H:%M:%S.%f")[:-3]

            # -------- relative time --------
            now = datetime.now()
            diff = now - dt

            if diff.days == 0:
                if diff.seconds < 60:
                    relative_time = "Just now"
                elif diff.seconds < 3600:
                    relative_time = f"{diff.seconds // 60}m ago"
                else:
                    relative_time = f"{diff.seconds // 3600}h ago"
            elif diff.days == 1:
                relative_time = "Yesterday"
            elif diff.days < 7:
                relative_time = f"{diff.days}d ago"
            else:
                relative_time = formatted_time

            # -------- mentions --------
            mentions = [f"@{m.get('handle')}" for m in body.get("mentions", [])]

            # -------- metrics normalization --------
            likes = metrics.get("likesCount", metrics.get("likeCount", 0))
            retweets = metrics.get("retweetsCount", metrics.get("retweetCount", 0))
            replies = metrics.get("repliesCount", metrics.get("replyCount", 0))
            bookmarks = metrics.get("bookmarksCount", metrics.get("bookmarkCount", 0))

            # -------- quoted tweet --------
            quoted = tweet.get("quoted")
            quoted_info = None

            if quoted:
                quoted_info = {
                    "id": quoted.get("id"),
                    "username": quoted.get("handle"),
                    "text": quoted.get("body", {}).get("text", ""),
                }

            twitter_url = f"https://x.com/{author.get('handle', 'unknown')}/status/{tweet_id}"

            tweet_data = {
                "id": tweet_id,
                "original_id": tweet_id,
                "twitter_url": twitter_url,
                "type": tweet.get("type", "TWEET"),
                "timestamp": timestamp_ms,
                "formatted_time": formatted_time,
                "relative_time": relative_time,
                "received_time": received_time,
                "author": {
                    "name": profile.get("name", "Unknown"),
                    "username": author.get("handle", "unknown"),
                    "avatar": profile.get("avatar", ""),
                    "verified": author.get("verified", False),
                    "following": author.get("metrics", {}).get("following", 0),
                    "followers": author.get("metrics", {}).get("followers", 0),
                },
                "content": {
                    "text": body.get("text", ""),
                    "mentions": mentions,
                },
                "subtweet": {
                    "content": subtweet_content,
                    "author": subtweet_author,
                } if subtweet_content else None,
                "stats": {
                    "likes": int(likes),
                    "retweets": int(retweets),
                    "replies": int(replies),
                    "bookmarks": int(bookmarks),
                },
                "replying_to": replying_to,
                "quoted": quoted_info,
                "media": tweet.get("media", {}),
            }

            print("🧵 PARSED TWEET:")
            print("=" * 80)
            pprint(tweet_data)
            print("=" * 80)

        except Exception as e:
            print(f"❌ Error processing tweet: {e}")
            import traceback
            traceback.print_exc()

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

# ================== MAIN SCRIPT ==================
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--headless=new",  # ✅ NEW headless mode
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

        # Remove navigator.webdriver
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        await page.goto(URL)
        print("🌍 Opened Padre.gg")
        await page.screenshot(path="homepage.png")

        # Click Google login
        google_btn = await page.wait_for_selector("//button[@data-testid='gmail-login-button']", timeout=30000)
        await google_btn.scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await google_btn.click()
        print("✅ Google login button clicked")

        # Handle popup
        popup = await context.wait_for_event("page")
        await popup.wait_for_load_state()
        # Remove webdriver in popup too
        await popup.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await popup.screenshot(path="google_popup.png")
        print("📸 Screenshot saved: google_popup.png")

        await submit_google_credentials(popup, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        await page.bring_to_front()
        await wait_for_navigation(page)
        await check_retry(page)
        await handle_secondary_login(page, SECONDARY_PASSWORD)

        # Hook WebSockets
        page.on("websocket", lambda ws: handle_ws(ws))
        print("📡 Listening for WebSocket frames...")
        await page.reload()
        await asyncio.sleep(10 ** 9)

asyncio.run(main())
