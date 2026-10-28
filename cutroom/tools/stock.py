"""Search and download Creative Commons media, with credits.

Sources:
  openverse   images, no key needed
  wikimedia   images, no key needed
  pexels      images and video, needs PEXELS_API_KEY (free)
  pixabay     images and video, needs PIXABAY_API_KEY (free)

Every download returns a credit record. The Capture agent collects them
into credits.json next to the final video.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

UA = {"User-Agent": "Cutroom/0.1 (local video tool; https://openverse.org)"}
# Licenses that allow commercial reuse and modification.
SAFE_LICENSES = {"cc0", "pdm", "by", "by-sa"}


def _openverse(query: str, kind: str, n: int, orientation: str | None) -> list[dict]:
    if kind != "image":
        return []
    params = {"q": query, "page_size": n * 3, "license": ",".join(SAFE_LICENSES), "mature": "false"}
    if orientation:
        params["aspect_ratio"] = {"landscape": "wide", "portrait": "tall", "square": "square"}[orientation]
    r = requests.get("https://api.openverse.org/v1/images/", params=params, headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json().get("results", []):
        if (it.get("width") or 0) < 1200:
            continue
        out.append({
            "source": "openverse", "kind": "image", "url": it["url"],
            "width": it.get("width"), "height": it.get("height"),
            "title": it.get("title"), "author": it.get("creator"),
            "license": f"CC {it['license'].upper()} {it.get('license_version') or ''}".strip(),
            "page": it.get("foreign_landing_url"),
        })
    return out[:n]


def _wikimedia(query: str, kind: str, n: int, orientation: str | None) -> list[dict]:
    if kind != "image":
        return []
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": n * 3,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 2400,
    }
    r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    for page in (r.json().get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = (meta.get("LicenseShortName", {}).get("value") or "").lower()
        if not any(tag in lic for tag in ("cc0", "public domain", "cc by")) or "nc" in lic or "nd" in lic:
            continue
        if (info.get("width") or 0) < 1200:
            continue
        out.append({
            "source": "wikimedia", "kind": "image", "url": info.get("thumburl") or info.get("url"),
            "width": info.get("thumbwidth") or info.get("width"), "height": info.get("thumbheight") or info.get("height"),
            "title": page.get("title"), "author": _strip_html(meta.get("Artist", {}).get("value", "")),
            "license": meta.get("LicenseShortName", {}).get("value"), "page": info.get("descriptionurl"),
        })
    return out[:n]


def _pexels(query: str, kind: str, n: int, orientation: str | None) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    path = "videos/search" if kind == "video" else "v1/search"
    params = {"query": query, "per_page": n}
    if orientation:
        params["orientation"] = orientation
    r = requests.get(f"https://api.pexels.com/{path}", params=params, headers={"Authorization": key}, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json().get("videos" if kind == "video" else "photos", []):
        if kind == "video":
            files = sorted(it["video_files"], key=lambda f: f.get("width") or 0)
            best = next((f for f in files if (f.get("width") or 0) >= 1920), files[-1])
            url, w, h = best["link"], best.get("width"), best.get("height")
            author = it["user"]["name"]
        else:
            url, w, h, author = it["src"]["original"], it["width"], it["height"], it["photographer"]
        out.append({"source": "pexels", "kind": kind, "url": url, "width": w, "height": h,
                    "title": it.get("alt") or query, "author": author, "license": "Pexels License", "page": it["url"]})
    return out


def _pixabay(query: str, kind: str, n: int, orientation: str | None) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    base = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    params = {"key": key, "q": query, "per_page": max(3, n), "safesearch": "true"}
    if orientation and kind == "image":
        params["orientation"] = {"landscape": "horizontal", "portrait": "vertical"}.get(orientation, "all")
    r = requests.get(base, params=params, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json().get("hits", [])[:n]:
        if kind == "video":
            v = it["videos"].get("large") or it["videos"]["medium"]
            url, w, h = v["url"], v["width"], v["height"]
        else:
            url, w, h = it.get("largeImageURL"), it.get("imageWidth"), it.get("imageHeight")
        out.append({"source": "pixabay", "kind": kind, "url": url, "width": w, "height": h,
                    "title": it.get("tags"), "author": it.get("user"), "license": "Pixabay Content License",
                    "page": it.get("pageURL")})
    return out


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s or "").strip()


SOURCES = {"openverse": _openverse, "wikimedia": _wikimedia, "pexels": _pexels, "pixabay": _pixabay}
DEFAULT_ORDER = ("pexels", "pixabay", "openverse", "wikimedia")


def search(query: str, kind: str = "image", n: int = 5, orientation: str | None = None,
           sources: tuple[str, ...] = DEFAULT_ORDER) -> list[dict]:
    """Search sources in order. Sources without a key are skipped quietly."""
    results = []
    for name in sources:
        try:
            results += SOURCES[name](query, kind, n, orientation)
        except requests.RequestException as e:
            print(f"  stock: {name} failed ({e.__class__.__name__}), trying next source")
        if len(results) >= n:
            break
    return results[:n]


def download(item: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = ".mp4" if item["kind"] == "video" else Path(item["url"].split("?")[0]).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4"}:
        ext = ".jpg"
    path = out_dir / f"{item['source']}_{hashlib.sha1(item['url'].encode()).hexdigest()[:10]}{ext}"
    if not path.exists():
        with requests.get(item["url"], headers=UA, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
    return {**item, "path": str(path)}


def fetch(query: str, out_dir: Path, kind: str = "image", orientation: str | None = None) -> dict:
    """Search and download the best match. Raises if nothing usable is found."""
    for item in search(query, kind=kind, n=4, orientation=orientation):
        try:
            return download(item, out_dir)
        except requests.RequestException:
            continue
    raise LookupError(f"No {kind} found for '{query}'")
