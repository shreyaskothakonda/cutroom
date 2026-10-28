"""Website capture with headless Chromium.

Produces a viewport shot and a full-page shot. Scenes animate the
full-page shot (scrolling, zooming), which keeps renders deterministic.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

# Hide common cookie and consent overlays so they do not cover the page.
_HIDE_OVERLAYS = """
[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i],
[aria-label*="cookie" i], [id*="onetrust" i], .cc-window, #CybotCookiebotDialog
{ display: none !important; }
"""


def capture(
    url: str,
    out_dir: Path,
    name: str = "site",
    width: int = 1440,
    height: int = 900,
    max_height: int = 6000,
    wait_ms: int = 1500,
    dark: bool = False,
    mobile: bool = False,
) -> dict:
    """Capture `url`. Returns paths and pixel sizes of both shots.

    mobile=True uses a phone viewport at 2x, for 9:16 scenes.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    viewport_png = out_dir / f"{name}_viewport.png"
    full_png = out_dir / f"{name}_full.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        device = dict(p.devices["iPhone 15"]) if mobile else {
            "viewport": {"width": width, "height": height}, "device_scale_factor": 1,
        }
        device.pop("default_browser_type", None)
        ctx = browser.new_context(
            **device,
            color_scheme="dark" if dark else "light",
            reduced_motion="reduce",
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.add_style_tag(content=_HIDE_OVERLAYS)
        # Scroll through once so lazy images load, then return to the top.
        page.evaluate(
            """async (maxH) => {
                const step = innerHeight * 0.8;
                for (let y = 0; y < Math.min(document.body.scrollHeight, maxH); y += step) {
                    scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
                }
                scrollTo(0, 0);
            }""",
            max_height,
        )
        page.wait_for_timeout(wait_ms)
        title = page.title()
        page.screenshot(path=str(viewport_png))
        page.screenshot(path=str(full_png), full_page=True)
        browser.close()

    with Image.open(full_png) as im:
        if im.height > max_height:
            im.crop((0, 0, im.width, max_height)).save(full_png)
        full_size = Image.open(full_png).size

    return {
        "url": url,
        "title": title,
        "viewport": str(viewport_png),
        "full": str(full_png),
        "width": full_size[0],
        "height": full_size[1],
    }
