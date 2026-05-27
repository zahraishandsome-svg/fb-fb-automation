"""
Gets Mama Roses page token using the Zahra Chrome profile session.
Navigates FB as logged-in user, tries BM login, then fetches page token.
"""

import os, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(os.environ["TEMP"]) / "zahra_chrome_root" / "Default"
SCREENSHOTS = Path("fb_dev_screenshots")
SCREENSHOTS.mkdir(exist_ok=True)
MAMA_ROSES_ID = "1108191409035961"


def ss(page, name):
    p = str(SCREENSHOTS / f"{name}.png")
    page.screenshot(path=p, full_page=True)
    print(f"  Screenshot: {p}")


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=["--no-first-run", "--start-maximized", "--no-sandbox"],
        )
        page = context.new_page()

        # Step 1: Land on FB
        print("Loading facebook.com...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(3000)

        if "login" in page.url.lower():
            ss(page, "not_logged_in")
            print("Not logged in! Check screenshot.")
            context.close()
            return

        print(f"Logged in. URL: {page.url}")

        # Step 2: Navigate to BM login via facebook.com (uses existing session)
        print("\nNavigating to Business Manager via facebook.com...")
        page.goto("https://www.facebook.com/business/help", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # Go directly to BM
        page.goto("https://business.facebook.com/", wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(4000)
        ss(page, "01_bm")
        print(f"BM URL: {page.url}")

        # If still on login page, try clicking "Continue as [name]"
        if "login" in page.url.lower() or "loginpage" in page.url.lower():
            print("BM login page — trying to continue with FB account...")
            try:
                # Look for "Continue" or "Log in with Facebook" button
                for btn_text in ["Continue", "Log In", "Log in with Facebook", "Continue as"]:
                    btns = page.get_by_text(btn_text, exact=False).all()
                    if btns:
                        btns[0].click()
                        page.wait_for_timeout(3000)
                        print(f"Clicked '{btn_text}'")
                        break
            except Exception as e:
                print(f"Button click error: {e}")
            ss(page, "02_bm_after_login")
            print(f"URL after: {page.url}")

        # Step 3: Navigate to Mama Roses page in BM
        print("\nGoing to Mama Roses in BM...")
        page.goto(f"https://business.facebook.com/settings/pages/{MAMA_ROSES_ID}",
                  wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(4000)
        ss(page, "03_mama_roses_bm")
        print(f"URL: {page.url}")

        # Step 4: Try getting page access token via Graph API from authenticated browser
        print("\nFetching page tokens via Graph API (browser-authenticated)...")

        # Navigate to a page that uses FB JS SDK
        page.goto("https://developers.facebook.com/tools/explorer/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # Use FB JS SDK in the page to get an access token
        token_result = page.evaluate("""
            async () => {
                // Try fetching /me/accounts via the browser's FB session cookie
                try {
                    const r = await fetch('https://graph.facebook.com/v19.0/me/accounts?fields=id,name,access_token&limit=100&__cppo=1', {
                        credentials: 'include',
                        headers: { 'Accept': 'application/json' }
                    });
                    return await r.json();
                } catch(e) {
                    return { fetch_error: e.toString() };
                }
            }
        """)
        print("Token fetch result:", json.dumps(token_result, indent=2)[:800])

        # Also check what pages are visible
        ss(page, "04_explorer")

        # Step 5: Navigate to Mama Roses page directly and check admin options
        print("\nNavigating to Mama Roses page directly...")
        page.goto(f"https://www.facebook.com/profile.php?id={MAMA_ROSES_ID}",
                  wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        ss(page, "05_mama_roses_page")
        print(f"URL: {page.url}")

        page_text = page.evaluate("() => document.body.innerText")
        print(f"Has 'Mama Roses': {'Mama Roses' in page_text or 'mama' in page_text.lower()}")

        print("\nDone. Check fb_dev_screenshots/ for all screenshots.")
        context.close()


if __name__ == "__main__":
    run()
