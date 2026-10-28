"""Render an HTML scene to an mp4, one exact frame at a time.

Contract with the scene page (see scenes/lib/runtime.js):
  window.__SCENE__   injected before load: width, height, fps, duration, params, words
  window.__ready     promise that resolves once assets are loaded
  window.renderFrame(t)  draws the frame at time t (seconds)
  window.__layout()  boxes of [data-qa] elements, for overlap QA
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

from cutroom.tools.server import StaticServer

# Frames at which the layout is sampled for QA, as fractions of the scene.
_LAYOUT_SAMPLES = (0.25, 0.5, 0.75, 0.95)


def render_scene(
    html: Path,
    out_mp4: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    params: dict | None = None,
    words: list | None = None,
    server: StaticServer | None = None,
) -> dict:
    """Render `html` to `out_mp4` (silent). Returns frame count and layout samples."""
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, round(duration * fps))
    scene = {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "params": params or {},
        "words": words or [],
    }

    own_server = server is None
    if own_server:
        server = StaticServer().__enter__()
    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart",
            str(out_mp4),
        ],
        stdin=subprocess.PIPE,
    )
    layout = []
    console_errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.add_init_script(f"window.__SCENE__ = {json.dumps(scene)};")
            page.goto(server.url_for(html), wait_until="load")
            page.wait_for_function("window.__ready !== undefined", timeout=20000)
            page.evaluate("window.__ready")
            sample_at = {min(n_frames - 1, int(f * n_frames)) for f in _LAYOUT_SAMPLES}
            for i in range(n_frames):
                t = i / fps
                page.evaluate("t => window.renderFrame(t)", t)
                ff.stdin.write(page.screenshot(type="jpeg", quality=95))
                if i in sample_at:
                    layout.append({"t": round(t, 3), "boxes": page.evaluate("window.__layout()")})
            browser.close()
    finally:
        ff.stdin.close()
        ff.wait()
        if own_server:
            server.__exit__(None, None, None)
    if ff.returncode != 0:
        raise RuntimeError(f"ffmpeg failed rendering {html}")
    if console_errors:
        raise RuntimeError(f"Scene {html.name} threw: {console_errors[0]}")
    return {"mp4": str(out_mp4), "frames": n_frames, "layout": layout}
