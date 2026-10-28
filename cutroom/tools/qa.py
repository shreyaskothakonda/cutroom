"""Deterministic QA checks on a finished video. No tokens.

Checks:
  format       resolution and fps match the target
  av_sync      audio and video lengths agree
  blank        black or flat frames (ffmpeg blackdetect plus a variance scan)
  frozen       long stretches with no change (ffmpeg freezedetect)
  silence      long gaps in the voice track (ffmpeg silencedetect)
  loudness     integrated loudness near -16 LUFS
  overlap      labelled elements that collide or leave the safe area
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np


def _ffmpeg_log(args: list[str]) -> str:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"], capture_output=True, text=True)
    return p.stderr


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def check_format(path: Path, width: int, height: int, fps: int) -> dict:
    info = _probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    ok = v["width"] == width and v["height"] == height and abs(num / den - fps) < 0.01
    return {"ok": ok, "width": v["width"], "height": v["height"], "fps": round(num / den, 3)}


def check_av_sync(path: Path, tolerance: float = 0.15) -> dict:
    info = _probe(path)
    durs = {s["codec_type"]: float(s.get("duration", info["format"]["duration"])) for s in info["streams"]}
    if "audio" not in durs:
        return {"ok": False, "reason": "no audio stream"}
    drift = abs(durs["video"] - durs["audio"])
    return {"ok": drift <= tolerance, "video": durs["video"], "audio": durs["audio"], "drift": round(drift, 3)}


def check_blank(path: Path, min_std: float = 4.0, samples_per_sec: float = 2) -> dict:
    """Black runs from ffmpeg plus low-variance frames found by sampling."""
    log = _ffmpeg_log(["-i", str(path), "-vf", "blackdetect=d=0.2:pix_th=0.08", "-an"])
    black = [
        {"start": float(a), "end": float(b)}
        for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    ]
    w, h = 160, 90
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"fps={samples_per_sec},scale={w}:{h},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)
    flat = [round(i / samples_per_sec, 2) for i, f in enumerate(frames) if f.std() < min_std]
    return {"ok": not black and not flat, "black": black, "flat_at": flat}


def check_frozen(path: Path, max_still: float = 4.0) -> dict:
    log = _ffmpeg_log(["-i", str(path), "-vf", f"freezedetect=n=0.0008:d={max_still}", "-an"])
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
    return {"ok": not starts, "frozen_at": starts}


def check_silence(path: Path, max_gap: float = 1.6, skip_tail: float = 1.0) -> dict:
    total = float(_probe(path)["format"]["duration"])
    log = _ffmpeg_log(["-i", str(path), "-af", f"silencedetect=n=-45dB:d={max_gap}", "-vn"])
    gaps = [
        {"start": float(a), "end": float(b)}
        for a, b in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", log)
    ]
    # A quiet first beat or outro tail is fine. Gaps in the middle are not.
    gaps = [g for g in gaps if g["start"] > 0.5 and g["end"] < total - skip_tail]
    return {"ok": not gaps, "gaps": gaps}


def check_loudness(path: Path, target: float = -16.0, tolerance: float = 2.0) -> dict:
    log = _ffmpeg_log(["-i", str(path), "-af", "ebur128", "-vn"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    if not m:
        return {"ok": False, "reason": "no loudness reading"}
    lufs = float(m[-1])
    return {"ok": abs(lufs - target) <= tolerance, "lufs": lufs}


def _intersect(a: dict, b: dict) -> float:
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return max(0.0, w) * max(0.0, h)


def check_overlap(layouts: list[dict], width: int, height: int, safe: float = 0.04, min_area: float = 64) -> dict:
    """layouts: [{scene, t, boxes:[{id,x,y,w,h,visible,layer}]}]. Boxes on the same layer must not collide."""
    issues = []
    mx, my = width * safe, height * safe
    for snap in layouts:
        boxes = [b for b in snap["boxes"] if b.get("visible") and b["w"] > 1 and b["h"] > 1]
        for b in boxes:
            if b.get("layer") == "bg":
                continue
            if b["x"] < mx - 1 or b["y"] < my - 1 or b["x"] + b["w"] > width - mx + 1 or b["y"] + b["h"] > height - my + 1:
                issues.append({"scene": snap["scene"], "t": snap["t"], "kind": "outside_safe_area", "id": b["id"]})
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if a.get("layer", "fg") != b.get("layer", "fg") or a.get("layer") == "bg":
                    continue
                if _intersect(a, b) > min_area:
                    issues.append({"scene": snap["scene"], "t": snap["t"], "kind": "overlap", "ids": [a["id"], b["id"]]})
    return {"ok": not issues, "issues": issues}


def run_all(path: Path, width: int, height: int, fps: int, layouts: list[dict]) -> dict:
    path = Path(path)
    checks = {
        "format": check_format(path, width, height, fps),
        "av_sync": check_av_sync(path),
        "blank": check_blank(path),
        "frozen": check_frozen(path),
        "silence": check_silence(path),
        "loudness": check_loudness(path),
        "overlap": check_overlap(layouts, width, height),
    }
    return {"video": str(path), "ok": all(c["ok"] for c in checks.values()), "checks": checks}
