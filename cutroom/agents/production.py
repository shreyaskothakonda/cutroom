"""The four tool agents: Capture, Voice, Assembly, QA. No LLM, no tokens.

Each reads storyboard.json (plus earlier stage outputs) and writes its
own file in the run folder, so any stage can be re-run on its own.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from cutroom.project import FORMATS, LEAD_IN, SCENES_DIR, TAIL, Run, read_json, write_json
from cutroom.tools import align, assemble, capture, images, qa, render, stock, tts


def _key(data) -> str:
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _cached(run: Run, stage: str, path: Path, key: str):
    """Return the stage output if it was made from the same input."""
    if path.exists() and stage not in run.force and "all" not in run.force:
        data = read_json(path)
        if data.get("_key") == key:
            return data
    return None


class Capture:
    """Resolves every asset request into a local file and writes its path into params."""

    name = "capture"

    def run(self, run: Run, sb: dict) -> dict:
        out = run.path("storyboard.resolved.json")
        key = _key([sb["scenes"], sb["formats"]])
        if (hit := _cached(run, self.name, out, key)) is not None:
            return hit
        sb = json.loads(json.dumps(sb))
        assets = run.dir / "assets"
        credits = []
        portrait = "9x16" in sb["formats"]
        for s in sb["scenes"]:
            for a in s["assets"]:
                key = a["as"]
                if a["kind"] == "capture":
                    name = f"{s['id']}_{key}"
                    shot = capture.capture(a["url"], assets, name=name)
                    s["params"][key] = run.web_path(shot["full"])
                    s["params"].setdefault("url", a["url"])
                    if portrait:
                        phone = capture.capture(a["url"], assets, name=f"{name}_mobile", mobile=True)
                        s["params"][f"{key}_mobile"] = run.web_path(phone["full"])
                    run.log(self.name, f"{s['id']}: captured {a['url']}", title=shot["title"])
                elif a["kind"] == "stock":
                    item = stock.fetch(a["query"], assets / "stock", kind="image", orientation="landscape")
                    norm = images.normalise(Path(item["path"]))
                    s["params"][key] = run.web_path(norm["path"])
                    who = item.get("author") or "Unknown"
                    s["params"]["credit"] = f"{who} / {item['source'].title()} / {item['license']}"
                    credits.append({"scene": s["id"], **{k: item.get(k) for k in
                                    ("title", "author", "license", "source", "page", "url")}})
                    run.log(self.name, f"{s['id']}: stock '{a['query']}' from {item['source']}")
        write_json(run.path("out", "credits.json"), credits)
        write_json(out, {**sb, "_key": key})
        return sb


class Voice:
    """Speaks each scene, aligns words with Whisper, and sets scene durations."""

    name = "voice"

    def run(self, run: Run, sb: dict) -> dict:
        out = run.path("voice.json")
        v = sb["voice"]
        key = _key([v, [[s["id"], s["narration"], s["min_duration"]] for s in sb["scenes"]]])
        if (hit := _cached(run, self.name, out, key)) is not None:
            return hit
        result = {"_key": key, "scenes": {}}
        for s in sb["scenes"]:
            wav = run.path("voice", f"{s['id']}.wav")
            spoken = tts.speak(s["narration"], wav, engine=v["engine"], voice=v["voice"], speed=v["speed"])
            timing = align.align(wav, s["narration"], spoken["duration"], language=v.get("lang", "en"))
            words = [{**w, "start": round(w["start"] + LEAD_IN, 3), "end": round(w["end"] + LEAD_IN, 3)}
                     for w in timing["words"]]
            duration = round(max(s["min_duration"], LEAD_IN + spoken["duration"] + TAIL), 2)
            result["scenes"][s["id"]] = {
                "wav": str(wav), "voice_seconds": spoken["duration"], "duration": duration,
                "words": words, "align": timing["method"], "engine": spoken["engine"],
            }
            run.log(self.name, f"{s['id']}: {spoken['duration']:.1f}s via {spoken['engine']}, timing by {timing['method']}")
        result["total"] = round(sum(x["duration"] for x in result["scenes"].values()), 2)
        write_json(out, result)
        return result


def _scene_key(html: Path, scene: dict, vo: dict, w: int, h: int, fps: int) -> str:
    """Changes when anything that affects the pixels changes."""
    lib = sorted((SCENES_DIR / "lib").glob("*"))
    blob = json.dumps([scene["params"], vo["words"], vo["duration"], w, h, fps]).encode()
    for f in [html, *lib]:
        blob += f.read_bytes()
    return hashlib.sha1(blob).hexdigest()


class Assembly:
    """Renders every scene per format, joins them and lays the voice track under them."""

    name = "assembly"

    def __init__(self, workers: int = 3):
        self.workers = workers

    def run(self, run: Run, sb: dict, vo: dict) -> dict:
        slug = run.dir.name
        outputs = {}
        for fmt in sb["formats"]:
            w, h = FORMATS[fmt]
            fps = sb["fps"]
            renders, jobs = {}, {}
            # Playwright's sync API deadlocks when several threads start browsers at
            # once, so each scene renders in its own process with its own server.
            with ProcessPoolExecutor(self.workers) as pool:
                for scene in sb["scenes"]:
                    v = vo["scenes"][scene["id"]]
                    html = SCENES_DIR / f"{scene['template']}.html"
                    mp4 = run.path("render", fmt, f"{scene['id']}.mp4")
                    meta = mp4.with_suffix(".json")
                    key = _scene_key(html, scene, v, w, h, fps)
                    if mp4.exists() and meta.exists() and read_json(meta).get("key") == key and self.name not in run.force:
                        renders[scene["id"]] = read_json(meta)
                        continue
                    fut = pool.submit(render.render_scene, html, mp4, w, h, fps, v["duration"],
                                      scene["params"], v["words"])
                    jobs[scene["id"]] = (fut, key, meta)
                for sid, (fut, key, meta) in jobs.items():
                    r = {"key": key, "scene": sid, **fut.result()}
                    write_json(meta, r)
                    renders[sid] = r
                    run.log(self.name, f"{fmt} {sid}: rendered {r['frames']} frames")
            renders = [renders[s["id"]] for s in sb["scenes"]]

            silent = run.path("render", fmt, "_silent.mp4")
            assemble.concat([r["mp4"] for r in renders], silent)
            clips, t = [], 0.0
            for s in sb["scenes"]:
                v = vo["scenes"][s["id"]]
                clips.append({"wav": v["wav"], "offset": t + LEAD_IN, "duration": v["duration"]})
                t += v["duration"]
            track = assemble.voice_track(clips, run.path("render", fmt, "_voice.wav"))
            final = run.path("out", f"{slug}_{fmt}.mp4")
            assemble.mux(silent, track, final)
            layouts = [{"scene": r["scene"], **snap} for r in renders for snap in r["layout"]]
            write_json(run.path("render", fmt, "_layouts.json"), layouts)
            assemble.contact_sheet(final, run.path("out", f"{slug}_{fmt}_sheet.png"))
            outputs[fmt] = {"video": str(final), "layouts": layouts, "seconds": round(t, 2)}
            run.log(self.name, f"{fmt}: {final.name} ({t:.1f}s)")
        return outputs


class QA:
    name = "qa"

    def run(self, run: Run, sb: dict, outputs: dict) -> dict:
        report = {}
        for fmt, o in outputs.items():
            w, h = FORMATS[fmt]
            r = qa.run_all(Path(o["video"]), w, h, sb["fps"], o["layouts"])
            report[fmt] = r
            failed = [k for k, c in r["checks"].items() if not c["ok"]]
            run.log(self.name, f"{fmt}: {'PASS' if r['ok'] else 'FAIL ' + ', '.join(failed)}")
        report["ok"] = all(r["ok"] for r in report.values())
        write_json(run.path("out", "qa.json"), report)
        return report
