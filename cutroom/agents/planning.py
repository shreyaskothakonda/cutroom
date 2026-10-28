"""The three LLM agents: Planner, Scriptwriter, Scene designer.

They only write JSON. Each one sees just what it needs, which keeps
prompts short and token use low.
"""

from __future__ import annotations

import json

from cutroom.project import CATALOG, Run, StoryboardError, read_json, validate_storyboard, write_json

HOUSE_STYLE = (
    "Write for the ear. Short sentences. Plain words. No em dashes. No hype words like "
    "revolutionary, game-changing or unlock. One idea per scene."
)


def _catalog_summary() -> str:
    return "\n".join(f"- {name}: {spec['use']}" for name, spec in CATALOG.items())


class Planner:
    name = "planner"
    system = (
        "You are the planner on a small video team. You turn a brief into a scene plan. "
        "You reply with JSON only."
    )

    def run(self, run: Run) -> dict:
        out = run.path("plan.json")
        if run.done(self.name, out):
            return read_json(out)
        b = run.brief
        seconds = b.get("length_seconds", 30)
        prompt = f"""Brief:
{json.dumps(b, indent=2)}

Scene templates you can use:
{_catalog_summary()}

Plan a video of about {seconds} seconds. Narration runs at about 2.6 words per second.
Use 4 to 7 scenes. Open with a title or a strong visual. Close with an outro.
If the brief names a URL, show it with the website template.
Mix templates so no two neighbours look the same.

Reply with JSON:
{{"title": str, "angle": str, "audience": str,
  "scenes": [{{"id": "s1", "template": str, "seconds": number, "purpose": str}}]}}"""
        plan = run.llm.json(self.name, self.system, prompt)
        write_json(out, plan)
        run.log(self.name, f"planned {len(plan['scenes'])} scenes: {plan['title']}")
        return plan


class Scriptwriter:
    name = "scriptwriter"
    system = f"You are the scriptwriter on a small video team. {HOUSE_STYLE} You reply with JSON only."

    def run(self, run: Run, plan: dict) -> dict:
        out = run.path("script.json")
        if run.done(self.name, out):
            return read_json(out)
        prompt = f"""Plan:
{json.dumps(plan, indent=2)}

Tone: {run.brief.get('tone', 'clear and warm')}

Write the voiceover for each scene. Aim for seconds x 2.6 words per scene.
Spell out numbers and symbols the way they should be spoken.

Reply with JSON:
{{"scenes": [{{"id": "s1", "narration": str}}]}}"""
        script = run.llm.json(self.name, self.system, prompt)
        write_json(out, script)
        words = sum(len(s["narration"].split()) for s in script["scenes"])
        run.log(self.name, f"wrote {words} words of narration")
        return script


class SceneDesigner:
    name = "scene_designer"
    system = (
        "You are the scene designer on a small video team. You choose on-screen text and assets "
        "for each scene. On-screen text is short and never repeats the narration word for word. "
        "You reply with JSON only."
    )

    def run(self, run: Run, plan: dict, script: dict) -> dict:
        out = run.path("storyboard.json")
        if run.done(self.name, out):
            return validate_storyboard(read_json(out))
        narration = {s["id"]: s["narration"] for s in script["scenes"]}
        scenes = [{**s, "narration": narration.get(s["id"], "")} for s in plan["scenes"]]
        prompt = f"""Scenes with narration:
{json.dumps(scenes, indent=2)}

Template specs (params and assets each template needs):
{json.dumps(CATALOG, indent=2)}

For every scene, fill the template params and list its assets.
Stock queries must name things a camera can see.
Keep the same id, template and narration.

Reply with JSON:
{{"scenes": [{{"id": str, "template": str, "narration": str, "params": {{}}, "assets": []}}]}}"""
        b = run.brief
        for attempt in range(2):
            designed = run.llm.json(self.name, self.system, prompt)
            sb = {
                "title": plan.get("title", b.get("topic", "Untitled")),
                "formats": b.get("formats", ["16x9", "9x16"]),
                "fps": b.get("fps", 30),
                "voice": b.get("voice", {}),
                "scenes": designed["scenes"],
            }
            try:
                sb = validate_storyboard(sb)
                break
            except StoryboardError as e:
                if attempt:
                    raise
                run.log(self.name, f"storyboard invalid, asking again: {e}")
                prompt += f"\n\nYour last storyboard had these problems, fix them: {e}"
        write_json(out, sb)
        run.log(self.name, "storyboard ready", scenes=[s["template"] for s in sb["scenes"]])
        return sb
