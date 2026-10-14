"""
DOM Explorer — discover Renfe's current booking form selectors.

Run this in NON-headless mode to visually inspect the Renfe website
and discover the correct CSS selectors for each step of the booking flow.

Usage:
    cd backend
    source ../venv/bin/activate
    python -m scripts.explore_dom

This script will:
1. Open renfe.com in a visible browser
2. Log all interactive elements found
3. Try to fill the search form
4. Take screenshots at each step
5. Save page HTML for offline analysis
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s │ %(message)s")
logger = logging.getLogger("dom-explorer")

OUTPUT_DIR = Path("/tmp/renfe_dom_explorer")
OUTPUT_DIR.mkdir(exist_ok=True)


async def explore():
    """Run the DOM exploration."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Show the browser!
            slow_mo=300,     # Slow down so we can see what's happening
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )
        # Anti-detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        # ── Step 1: Load renfe.com ──
        logger.info("═══ STEP 1: Loading renfe.com ═══")
        await page.goto("https://www.renfe.com/es/es", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Save screenshot
        await page.screenshot(path=str(OUTPUT_DIR / "01_homepage.png"), full_page=True)
        logger.info("Screenshot saved: 01_homepage.png")

        # ── Accept cookies ──
        logger.info("═══ Looking for cookie consent ═══")
        cookie_selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Aceptar')",
            "button:has-text('Accept')",
            ".onetrust-accept-btn-handler",
        ]
        for sel in cookie_selectors:
            try:
                btn = page.locator(sel)
                if await btn.is_visible(timeout=2000):
                    logger.info("  ✅ Found cookie button: %s", sel)
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        await page.screenshot(path=str(OUTPUT_DIR / "02_after_cookies.png"))

        # ── Step 2: Discover form elements ──
        logger.info("═══ STEP 2: Discovering form elements ═══")

        # Find all inputs
        inputs = await page.query_selector_all("input")
        logger.info("Found %d <input> elements:", len(inputs))
        for i, inp in enumerate(inputs):
            attrs = await page.evaluate("""(el) => {
                return {
                    type: el.type,
                    name: el.name,
                    id: el.id,
                    placeholder: el.placeholder,
                    formControlName: el.getAttribute('formcontrolname'),
                    ariaLabel: el.getAttribute('aria-label'),
                    className: el.className,
                    visible: el.offsetParent !== null,
                    value: el.value,
                };
            }""", inp)
            if attrs.get("visible"):
                logger.info("  input[%d]: %s", i, json.dumps(attrs, indent=2))

        # Find all buttons
        buttons = await page.query_selector_all("button")
        logger.info("Found %d <button> elements:", len(buttons))
        for i, btn in enumerate(buttons):
            attrs = await page.evaluate("""(el) => {
                return {
                    type: el.type,
                    id: el.id,
                    text: el.innerText.substring(0, 100),
                    className: el.className.substring(0, 200),
                    ariaLabel: el.getAttribute('aria-label'),
                    visible: el.offsetParent !== null,
                };
            }""", btn)
            if attrs.get("visible") and attrs.get("text", "").strip():
                logger.info("  button[%d]: %s", i, json.dumps(attrs, indent=2))

        # ── Step 3: Try to fill origin ──
        logger.info("═══ STEP 3: Trying to fill origin ═══")
        origin_selectors = [
            "input[placeholder*='origen']",
            "input[placeholder*='salida']",
            "input[placeholder*='departure']",
            "input[formcontrolname='origin']",
            "input[aria-label*='origen']",
            "input[aria-label*='salida']",
        ]

        origin_found = None
        for sel in origin_selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    logger.info("  ✅ Origin input found: %s", sel)
                    origin_found = sel
                    break
                else:
                    logger.info("  ❌ Not found: %s", sel)
            except Exception as e:
                logger.info("  ❌ Error with %s: %s", sel, e)

        if origin_found:
            await page.locator(origin_found).first.click()
            await page.wait_for_timeout(500)
            await page.locator(origin_found).first.fill("")
            await page.locator(origin_found).first.type("MADRID", delay=100)
            await page.wait_for_timeout(1500)

            await page.screenshot(path=str(OUTPUT_DIR / "03_origin_typed.png"))

            # Check for autocomplete dropdown
            autocomplete_selectors = [
                "ul.p-autocomplete-items li",
                ".rf-autocomplete__option",
                "[role='option']",
                ".cdk-overlay-container li",
                "mat-option",
                ".autocomplete-item",
                "li[class*='station']",
            ]
            for sel in autocomplete_selectors:
                try:
                    items = page.locator(sel)
                    count = await items.count()
                    if count > 0:
                        logger.info("  ✅ Autocomplete dropdown found: %s (%d items)", sel, count)
                        for j in range(min(count, 5)):
                            text = await items.nth(j).inner_text()
                            logger.info("    Item %d: %s", j, text.strip()[:80])

                        # Click first item
                        await items.first.click()
                        await page.wait_for_timeout(500)
                        break
                except Exception:
                    pass

        await page.screenshot(path=str(OUTPUT_DIR / "04_origin_selected.png"))

        # ── Step 4: Try to fill destination ──
        logger.info("═══ STEP 4: Trying to fill destination ═══")
        dest_selectors = [
            "input[placeholder*='destino']",
            "input[placeholder*='llegada']",
            "input[placeholder*='arrival']",
            "input[formcontrolname='destination']",
            "input[aria-label*='destino']",
            "input[aria-label*='llegada']",
        ]

        dest_found = None
        for sel in dest_selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    logger.info("  ✅ Destination input found: %s", sel)
                    dest_found = sel
                    break
                else:
                    logger.info("  ❌ Not found: %s", sel)
            except Exception as e:
                logger.info("  ❌ Error with %s: %s", sel, e)

        if dest_found:
            await page.locator(dest_found).first.click()
            await page.wait_for_timeout(500)
            await page.locator(dest_found).first.fill("")
            await page.locator(dest_found).first.type("BARCELONA", delay=100)
            await page.wait_for_timeout(1500)

            await page.screenshot(path=str(OUTPUT_DIR / "05_destination_typed.png"))

            # Click first autocomplete item
            for sel in autocomplete_selectors:
                try:
                    items = page.locator(sel)
                    if await items.count() > 0:
                        await items.first.click()
                        break
                except Exception:
                    pass

        await page.screenshot(path=str(OUTPUT_DIR / "06_destination_selected.png"))

        # ── Step 5: Find and click search button ──
        logger.info("═══ STEP 5: Looking for search button ═══")
        search_selectors = [
            "button[type='submit']",
            "button:has-text('Buscar')",
            "button:has-text('Buscar billete')",
            "button:has-text('Search')",
            "button.btn-primary",
            "button[class*='search']",
            "button[aria-label*='buscar']",
        ]

        for sel in search_selectors:
            try:
                btn = page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    text = await btn.first.inner_text()
                    logger.info("  ✅ Search button found: %s → '%s'", sel, text.strip()[:50])
            except Exception:
                pass

        # Click search
        logger.info("═══ Clicking search... ═══")
        try:
            search_btn = page.locator("button:has-text('Buscar')").first
            await search_btn.click()
            logger.info("  ✅ Search clicked")
        except Exception as e:
            logger.error("  ❌ Could not click search: %s", e)
            try:
                submit = page.locator("button[type='submit']").first
                await submit.click()
                logger.info("  ✅ Submit clicked (fallback)")
            except Exception as e2:
                logger.error("  ❌ Fallback also failed: %s", e2)

        # Wait for results
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(OUTPUT_DIR / "07_search_results.png"), full_page=True)

        # ── Step 6: Analyze results page ──
        logger.info("═══ STEP 6: Analyzing results page ═══")
        logger.info("  Current URL: %s", page.url)

        # Save full page HTML
        html = await page.content()
        (OUTPUT_DIR / "results_page.html").write_text(html)
        logger.info("  Saved results HTML (%d chars)", len(html))

        # Look for train result elements
        result_selectors = [
            ".trayecto",
            ".journey-item",
            "[data-test='journey-item']",
            ".travel-list__item",
            "[class*='trayecto']",
            "[class*='journey']",
            "[class*='travel']",
            "tr[class*='result']",
            ".list-group-item",
            "article",
        ]

        for sel in result_selectors:
            try:
                items = page.locator(sel)
                count = await items.count()
                if count > 0:
                    logger.info("  ✅ Train results found: %s (%d items)", sel, count)
                    # Get first item's HTML for analysis
                    first_html = await items.first.evaluate("el => el.outerHTML")
                    logger.info("  First item HTML (%d chars): %s", len(first_html), first_html[:500])
            except Exception:
                pass

        # Look for pet icons
        pet_selectors = [
            "[class*='pet']",
            "[class*='mascota']",
            "img[alt*='mascota']",
            "img[alt*='pet']",
            "[class*='animal']",
            ".icon-pet",
        ]
        for sel in pet_selectors:
            try:
                items = page.locator(sel)
                count = await items.count()
                if count > 0:
                    logger.info("  🐾 Pet icon found: %s (%d instances)", sel, count)
            except Exception:
                pass

        # ── Done ──
        logger.info("═══════════════════════════════════════")
        logger.info("DOM exploration complete!")
        logger.info("Screenshots and HTML saved to: %s", OUTPUT_DIR)
        logger.info("═══════════════════════════════════════")

        # Keep browser open for manual inspection
        logger.info("Browser will stay open for 60 seconds for manual inspection...")
        logger.info("Press Ctrl+C to close earlier.")
        try:
            await page.wait_for_timeout(60000)
        except KeyboardInterrupt:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
