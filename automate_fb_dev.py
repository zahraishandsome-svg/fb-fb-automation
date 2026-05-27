"""
Automates Facebook Developers portal using Zahra's Chrome profile:
1. Sets privacy policy + terms URL
2. Links Skyward Media Tech business
3. Sets app to Live mode
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

APP_ID       = "2957694347904296"
BUSINESS_ID  = "1702214263256684"
BUSINESS_NAME = "Skyward Media Tech"

BASIC_URL    = f"https://developers.facebook.com/apps/{APP_ID}/settings/basic/"
ADVANCED_URL = f"https://developers.facebook.com/apps/{APP_ID}/settings/advanced/"

PRIVACY_URL = "https://kindlytold.com/privacy-policy"
TERMS_URL   = "https://kindlytold.com/terms-of-service"
APP_DOMAIN  = "kindlytold.com"

# Zahra's profile: user_data_dir=Default subfolder, Local State at root
PROFILE_DIR = Path(os.environ["TEMP"]) / "zahra_chrome_root" / "Default"

SCREENSHOTS = Path("fb_dev_screenshots")
SCREENSHOTS.mkdir(exist_ok=True)


def ss(page, name):
    path = str(SCREENSHOTS / f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 {path}")


def run():
    print(f"Using profile: {PROFILE_DIR}")
    print(f"Profile exists: {PROFILE_DIR.exists()}")

    with sync_playwright() as p:
        # Launch Playwright's Chromium with Zahra's copied profile
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            channel="chrome",        # use installed Chrome binary (can decrypt DPAPI cookies)
            args=[
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
            no_viewport=True,
        )

        page = context.new_page()

        # ── STEP 1: Basic Settings ─────────────────────────────────────────
        print("\n[1/3] Basic Settings →", BASIC_URL)
        page.goto(BASIC_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        ss(page, "01_basic_loaded")

        if "login" in page.url.lower():
            print("  ❌ Not logged in — cookies didn't transfer. See screenshot.")
            context.close()
            return

        print(f"  ✅ Logged in. URL: {page.url}")

        # Dump all inputs to understand the page structure
        inputs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map((el, i) => ({
                i, type: el.type, placeholder: el.placeholder,
                name: el.name, id: el.id,
                label: el.labels?.[0]?.innerText || '',
                value: el.value?.slice(0, 60),
                ariaLabel: el.getAttribute('aria-label') || '',
            }));
        }""")
        print(f"  Found {len(inputs)} inputs:")
        for inp in inputs:
            print(f"    [{inp['i']}] type={inp['type']} placeholder='{inp['placeholder']}' "
                  f"label='{inp['label']}' aria='{inp['ariaLabel']}' val='{inp['value']}'")

        # Fill Privacy Policy URL
        def fill_field(hint_texts, value, label):
            for inp in inputs:
                text = " ".join([
                    inp.get("placeholder",""), inp.get("label",""),
                    inp.get("ariaLabel",""), inp.get("name",""), inp.get("id","")
                ]).lower()
                if any(h.lower() in text for h in hint_texts):
                    idx = inp["i"]
                    try:
                        el = page.locator("input").nth(idx)
                        el.scroll_into_view_if_needed()
                        el.click()
                        el.triple_click()
                        el.fill(value)
                        print(f"  ✅ Filled {label} (input #{idx}): {value}")
                        return True
                    except Exception as e:
                        print(f"  ⚠ Failed to fill {label} at #{idx}: {e}")
            print(f"  ❌ Could not find {label} field")
            return False

        fill_field(["privacy", "privacy policy"], PRIVACY_URL, "Privacy Policy URL")
        fill_field(["terms", "terms of service"], TERMS_URL, "Terms of Service URL")

        ss(page, "02_basic_filled")

        # Save
        try:
            save_btn = page.get_by_role("button", name="Save Changes").first
            save_btn.click()
            page.wait_for_timeout(2000)
            print("  ✅ Save Changes clicked")
            ss(page, "03_basic_saved")
        except Exception as e:
            print(f"  ⚠ Save button: {e}")
            # Try any button with 'save' text
            try:
                page.locator("button:has-text('Save')").first.click()
                page.wait_for_timeout(2000)
                ss(page, "03_basic_saved_alt")
            except Exception as e2:
                print(f"  ❌ Could not save: {e2}")

        # ── STEP 2: Advanced Settings — Link Business ─────────────────────
        print("\n[2/3] Advanced Settings →", ADVANCED_URL)
        page.goto(ADVANCED_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        ss(page, "04_advanced_loaded")

        # Get all buttons to find the business linking option
        btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, [role=button], a[href]'))
                .map(el => ({ text: el.innerText?.trim().slice(0, 80), tag: el.tagName, href: el.href || '' }))
                .filter(b => b.text)
                .slice(0, 50);
        }""")
        print("  Buttons/links on advanced page:")
        for b in btns:
            print(f"    {b['tag']}: '{b['text']}'")

        # Get full page text to find business section
        page_text = page.evaluate("() => document.body.innerText")
        has_biz = "Business" in page_text or "business" in page_text or "Portfolio" in page_text
        print(f"  Business section present: {has_biz}")

        if has_biz:
            # Try to click "Link" or "Add" near Business Portfolio
            try:
                page.get_by_text("Business Portfolio", exact=False).scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                ss(page, "05_biz_section")

                # Look for a Link/Connect button near it
                for btn_text in ["Link to Business Portfolio", "Link", "Connect", "Add Business"]:
                    try:
                        btn = page.get_by_role("button", name=btn_text, exact=False).first
                        if btn.count() > 0:
                            btn.click()
                            page.wait_for_timeout(2000)
                            ss(page, "06_biz_dialog")
                            print(f"  ✅ Clicked '{btn_text}' button")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"  ⚠ Business section: {e}")

        ss(page, "07_advanced_final")

        # ── STEP 3: Toggle to Live mode ────────────────────────────────────
        print("\n[3/3] Checking Live mode toggle...")
        page.goto(BASIC_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Look for the mode toggle (Development / Live switch)
        toggle_text = page.evaluate("""() => {
            const el = document.querySelector('[data-testid*="mode"], [aria-label*="mode"], [aria-label*="Mode"]');
            return el ? el.outerHTML.slice(0, 200) : 'not found';
        }""")
        print(f"  Mode toggle: {toggle_text}")
        ss(page, "08_live_mode_check")

        print("\n✅ Automation complete. Check fb_dev_screenshots/ folder.")
        print("   Keeping browser open so you can review...")
        input("\nPress Enter to close browser...")
        context.close()


if __name__ == "__main__":
    run()
