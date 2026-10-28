"""Command line.

  cutroom make brief.yaml              brief to videos (LLM plans, tools build)
  cutroom render storyboard.json       storyboard to videos (no LLM)
  cutroom tool <name> ...              run one tool on its own
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def _formats(value: str | None):
    return [f.strip() for f in value.split(",")] if value else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cutroom")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="brief.yaml to finished videos")
    m.add_argument("brief", type=Path)
    m.add_argument("--llm", default="claude-cli", choices=["claude-cli", "anthropic", "manual"])
    m.add_argument("--model", default="sonnet")
    m.add_argument("--formats", help="comma list, e.g. 16x9,9x16")
    m.add_argument("--force", default="", help="comma list of stages to redo, or 'all'")
    m.add_argument("--workers", type=int, default=3)

    r = sub.add_parser("render", help="storyboard.json to finished videos, no LLM")
    r.add_argument("storyboard", type=Path)
    r.add_argument("--formats")
    r.add_argument("--force", default="")
    r.add_argument("--workers", type=int, default=3)

    t = sub.add_parser("tool", help="run a single tool")
    tools = t.add_subparsers(dest="tool", required=True)

    c = tools.add_parser("capture", help="screenshot a website")
    c.add_argument("url")
    c.add_argument("--out", type=Path, default=Path("captures"))
    c.add_argument("--name", default="site")
    c.add_argument("--mobile", action="store_true")

    s = tools.add_parser("stock", help="search (and optionally download) CC media")
    s.add_argument("query")
    s.add_argument("--kind", default="image", choices=["image", "video"])
    s.add_argument("--download", type=Path)

    v = tools.add_parser("tts", help="speak text to a wav")
    v.add_argument("text")
    v.add_argument("--out", type=Path, default=Path("speech.wav"))
    v.add_argument("--engine", default="kokoro")
    v.add_argument("--voice", default="af_heart")
    v.add_argument("--speed", type=float, default=1.0)

    a = tools.add_parser("align", help="word timings for a wav and its script")
    a.add_argument("wav", type=Path)
    a.add_argument("text")

    rd = tools.add_parser("render", help="render one scene template")
    rd.add_argument("template", help="name from scenes/catalog.json, or a path to an html file")
    rd.add_argument("--params", default="{}", help="JSON string or path to a JSON file")
    rd.add_argument("--seconds", type=float, default=5)
    rd.add_argument("--format", default="16x9")
    rd.add_argument("--fps", type=int, default=30)
    rd.add_argument("--out", type=Path, default=Path("scene.mp4"))

    q = tools.add_parser("qa", help="run QA checks on a video")
    q.add_argument("video", type=Path)
    q.add_argument("--format", default="16x9")
    q.add_argument("--fps", type=int, default=30)
    q.add_argument("--layouts", type=Path, help="layout samples from a render")

    args = ap.parse_args(argv)
    force = {x for x in getattr(args, "force", "").split(",") if x}

    if args.cmd == "make":
        from cutroom.orchestrator import make

        _print(make(args.brief, args.llm, args.model, force, args.workers, _formats(args.formats)))
    elif args.cmd == "render":
        from cutroom.orchestrator import render_storyboard

        _print(render_storyboard(args.storyboard, force, args.workers, _formats(args.formats)))
    elif args.tool == "capture":
        from cutroom.tools.capture import capture

        _print(capture(args.url, args.out, args.name, mobile=args.mobile))
    elif args.tool == "stock":
        from cutroom.tools import stock

        if args.download:
            _print(stock.fetch(args.query, args.download, kind=args.kind))
        else:
            _print(stock.search(args.query, kind=args.kind))
    elif args.tool == "tts":
        from cutroom.tools.tts import speak

        _print(speak(args.text, args.out, args.engine, args.voice, args.speed))
    elif args.tool == "align":
        from cutroom.tools.align import align
        from cutroom.tools.tts import wav_duration

        _print(align(args.wav, args.text, wav_duration(args.wav)))
    elif args.tool == "render":
        from cutroom.project import FORMATS, SCENES_DIR
        from cutroom.tools.render import render_scene

        html = Path(args.template) if args.template.endswith(".html") else SCENES_DIR / f"{args.template}.html"
        p = Path(args.params)
        params = json.loads(p.read_text() if p.suffix == ".json" and p.exists() else args.params)
        w, h = FORMATS[args.format]
        _print(render_scene(html.resolve(), args.out, w, h, args.fps, args.seconds, params))
    elif args.tool == "qa":
        from cutroom.project import FORMATS
        from cutroom.tools.qa import run_all

        w, h = FORMATS[args.format]
        layouts = json.loads(args.layouts.read_text()) if args.layouts else []
        report = run_all(args.video, w, h, args.fps, layouts)
        _print(report)
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
