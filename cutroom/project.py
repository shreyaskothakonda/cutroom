"""Run folder, formats, storyboard validation and the shared run context."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from cutroom import ROOT

SCENES_DIR = ROOT / "scenes"
CATALOG = json.loads((SCENES_DIR / "catalog.json").read_text())

FORMATS = {
    "16x9": (1920, 1080),
    "9x16": (1080, 1920),
}

# Breathing room around each line of narration, in seconds.
LEAD_IN = 0.35
TAIL = 0.6


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "video"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def read_json(path: Path):
    return json.loads(Path(path).read_text())


class StoryboardError(ValueError):
    pass


def validate_storyboard(sb: dict) -> dict:
    """Check a storyboard and fill defaults. Raises StoryboardError with every problem found."""
    problems = []
    sb.setdefault("formats", ["16x9", "9x16"])
    sb.setdefault("fps", 30)
    sb.setdefault("voice", {})
    sb["voice"] = {"engine": "kokoro", "voice": "af_heart", "speed": 1.0, **sb["voice"]}
    for f in sb["formats"]:
        if f not in FORMATS:
            problems.append(f"unknown format {f}")
    scenes = sb.get("scenes") or []
    if not scenes:
        problems.append("no scenes")
    seen = set()
    for i, s in enumerate(scenes):
        sid = s.setdefault("id", f"s{i + 1}")
        if sid in seen:
            problems.append(f"duplicate scene id {sid}")
        seen.add(sid)
        if s.get("template") not in CATALOG:
            problems.append(f"{sid}: unknown template {s.get('template')}")
            continue
        if not (s.get("narration") or "").strip():
            problems.append(f"{sid}: empty narration")
        s.setdefault("params", {})
        s.setdefault("assets", [])
        s.setdefault("min_duration", 3.0)
        for a in s["assets"]:
            if a.get("kind") not in {"capture", "stock"}:
                problems.append(f"{sid}: unknown asset kind {a.get('kind')}")
            if a.get("kind") == "capture" and not a.get("url"):
                problems.append(f"{sid}: capture asset needs a url")
            if a.get("kind") == "stock" and not a.get("query"):
                problems.append(f"{sid}: stock asset needs a query")
            a.setdefault("as", "image")
        needed = {a["as"] for a in CATALOG[s["template"]]["assets"]}
        have = {a.get("as") for a in s["assets"]} | set(s["params"])
        for key in needed - have:
            problems.append(f"{sid}: template {s['template']} needs asset '{key}'")
        if s["template"] == "bullets" and not isinstance(s["params"].get("items"), list):
            problems.append(f"{sid}: bullets needs params.items as a list")
    if problems:
        raise StoryboardError("; ".join(problems))
    return sb


@dataclass
class Run:
    """Everything one video run shares between agents."""

    dir: Path
    brief: dict = field(default_factory=dict)
    llm: object = None
    force: set = field(default_factory=set)

    def path(self, *parts) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def web_path(self, p: Path | str) -> str:
        """Absolute URL path for a file, as the scene pages see it."""
        return "/" + Path(p).resolve().relative_to(ROOT).as_posix()

    def log(self, agent: str, msg: str, **data) -> None:
        line = {"t": round(time.time(), 2), "agent": agent, "msg": msg, **data}
        with open(self.path("log.jsonl"), "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
        print(f"[{agent}] {msg}")

    def done(self, stage: str, path: Path) -> bool:
        return path.exists() and stage not in self.force and "all" not in self.force
