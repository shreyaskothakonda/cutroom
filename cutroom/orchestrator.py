"""Runs the agents in order and hands each one the previous stage's output."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import yaml

from cutroom import ROOT
from cutroom.agents import QA, Assembly, Capture, Planner, SceneDesigner, Scriptwriter, Voice
from cutroom.llm import LLM
from cutroom.project import Run, read_json, slugify, validate_storyboard, write_json


def _new_run(name: str, force: set) -> Run:
    d = ROOT / "runs" / slugify(name)
    d.mkdir(parents=True, exist_ok=True)
    return Run(dir=d, force=force)


def _produce(run: Run, sb: dict, workers: int) -> dict:
    started = time.time()
    sb = Capture().run(run, sb)
    vo = Voice().run(run, sb)
    outputs = Assembly(workers).run(run, sb, vo)
    report = QA().run(run, sb, outputs)
    summary = {
        "run": str(run.dir),
        "videos": {f: o["video"] for f, o in outputs.items()},
        "seconds": {f: o["seconds"] for f, o in outputs.items()},
        "qa_ok": report["ok"],
        "wall_seconds": round(time.time() - started, 1),
    }
    write_json(run.path("out", "summary.json"), summary)
    return summary


def make(brief_path: Path, llm_backend: str = "claude-cli", model: str = "sonnet",
         force: set | None = None, workers: int = 3, formats: list[str] | None = None) -> dict:
    """Brief to finished videos: plan, write, design, then the tool agents."""
    brief = yaml.safe_load(Path(brief_path).read_text())
    if formats:
        brief["formats"] = formats
    run = _new_run(brief.get("slug") or brief["topic"], force or set())
    run.brief = brief
    shutil.copy(brief_path, run.path("brief.yaml"))
    run.llm = LLM(llm_backend, model, workdir=run.path("llm", "_").parent)
    plan = Planner().run(run)
    script = Scriptwriter().run(run, plan)
    sb = SceneDesigner().run(run, plan, script)
    if formats:
        sb["formats"] = formats
    return _produce(run, sb, workers)


def render_storyboard(sb_path: Path, force: set | None = None, workers: int = 3,
                      formats: list[str] | None = None) -> dict:
    """Skip the LLM. Take a hand-written storyboard straight to video."""
    sb = validate_storyboard(read_json(sb_path))
    if formats:
        sb["formats"] = formats
    run = _new_run(sb.get("slug") or sb["title"], force or set())
    write_json(run.path("storyboard.json"), sb)
    return _produce(run, sb, workers)
