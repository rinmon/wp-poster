import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to URL...")
        await page.goto("https://x.com/elonmusk", wait_until="networkidle", timeout=60000)
        # We need the trending tweet or recent tweet from elon
        await page.wait_for_timeout(5000)
        
        # Taking screenshot for debugging
        await page.screenshot(path="x_debug.png")
        
        # Evaluate for images in timeline
        images = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img')).map(img => img.src).filter(src => src.includes('pbs.twimg.com/media'));
        }""")
        print("Found media:")
        for img in images:
            print(img)
            
        await browser.close()

asyncio.run(main())
