# Cutroom

Agents plan. Local tools build. A short brief becomes a narrated video in 16:9 and 9:16.

## Make a video with an AI agent

Paste this prompt into an AI coding agent in a new session. Replace the brief at the bottom with your own.

````text
You are making a short narrated video with Cutroom, a local video tool.
Repo: https://github.com/shreyaskothakonda/cutroom

Your job is to plan and write. Cutroom's local tools do everything else
(capture, voice, timing, rendering, assembly, QA). Do not write your own
rendering, TTS or ffmpeg code. Use the CLI.

1. SET UP (skip what is already done)
   git clone https://github.com/shreyaskothakonda/cutroom.git && cd cutroom
   uv venv --python 3.12 .venv
   uv pip install --python .venv -e '.[voice]'
   (cd vendor && npm install)
   Check: ffmpeg -version, and .venv/bin/cutroom --help.
   If Playwright has no browser: .venv/bin/playwright install chromium

2. READ THE SCENE CATALOG
   Open scenes/catalog.json. It lists the templates (title, website, photo,
   orb3d, bullets, outro), the params each takes and the assets each needs.
   Use only these templates and params.

3. WRITE THE STORYBOARD
   You are the planner, scriptwriter and scene designer. Write
   runs/<slug>.storyboard.json in this shape:
   {
     "title": "...", "slug": "<short-kebab-name>",
     "formats": ["16x9", "9x16"], "fps": 30,
     "voice": {"engine": "kokoro", "voice": "af_heart", "speed": 1.0},
     "scenes": [
       {"id": "s1", "template": "title", "narration": "...",
        "params": {"kicker": "...", "headline": "...", "sub": "..."}, "assets": []},
       {"id": "s2", "template": "website", "narration": "...",
        "params": {"kicker": "...", "title": "...", "url": "https://...", "scroll": 0.5},
        "assets": [{"kind": "capture", "url": "https://...", "as": "image"}]},
       {"id": "s3", "template": "photo", "narration": "...",
        "params": {"kicker": "...", "headline": "..."},
        "assets": [{"kind": "stock", "query": "concrete visual words", "as": "image"}]}
     ]
   }
   Rules:
   - 4 to 7 scenes. Open with title or a strong visual. End with outro.
     No two neighbouring scenes use the same template.
   - Narration runs about 2.6 words per second. Size each scene to that.
     Short sentences, plain spoken words, no em dashes, no hype words.
     Spell numbers and symbols the way they are said ("python dot org").
   - On-screen text is short (headlines 3 to 7 words) and never repeats
     the narration word for word.
   - Any URL in the brief goes in a website scene with a capture asset.
   - Stock queries name things a camera can see, not ideas.
   - bullets needs params.items as a list of 2 to 4 short strings.

4. RENDER
   .venv/bin/cutroom render runs/<slug>.storyboard.json
   This captures sites, fetches CC stock images with credits, speaks each
   scene with Kokoro, times every word with Whisper, renders each scene frame
   by frame, joins them, adds the voice track and runs QA. If it stops with a
   storyboard error, fix the JSON and run it again. Finished stages are cached.

5. CHECK THE RESULT
   Read runs/<slug>/out/qa.json. Every check must be ok: format, av_sync,
   blank, frozen, silence, loudness, overlap.
   Look at runs/<slug>/out/<slug>_16x9_sheet.png and <slug>_9x16_sheet.png.
   If something fails or looks wrong, change the storyboard (shorter text,
   another template, a better stock query, tighter narration) and render
   again. Use --force capture, voice or assembly only to redo a stage whose
   input did not change.

6. DELIVER
   Hand back runs/<slug>/out/<slug>_16x9.mp4 and <slug>_9x16.mp4, the
   storyboard you wrote, and runs/<slug>/out/credits.json for the stock media.

Useful single tools when you need them:
   .venv/bin/cutroom tool capture <url> --out captures [--mobile]
   .venv/bin/cutroom tool stock "<query>"
   .venv/bin/cutroom tool tts "<text>" --out test.wav
   .venv/bin/cutroom tool render <template> --params '<json>' --seconds 4 --format 9x16 --out test.mp4
   .venv/bin/cutroom tool qa <video.mp4> --format 16x9

BRIEF
Topic: <what the video is about>
Audience: <who it is for>
Length: about 30 seconds
Tone: <e.g. friendly, plain, confident>
Must include: <URLs to show, things to mention>
````

## Design

See [PRODUCT.md](PRODUCT.md).

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -e '.[voice]'
cd vendor && npm install && cd ..
```

Needs ffmpeg on PATH. Playwright uses its own Chromium (`.venv/bin/playwright install chromium` if it is missing).

Optional keys for more stock media: `PEXELS_API_KEY`, `PIXABAY_API_KEY`. Openverse and Wikimedia work with no key.

## Make a video

From a brief (the planning agents write the storyboard):

```bash
.venv/bin/cutroom make examples/python-first-language.yaml
```

LLM backends: `--llm claude-cli` (default, uses your Claude Code login), `--llm anthropic` (needs `ANTHROPIC_API_KEY`), `--llm manual` (writes each prompt to `runs/<slug>/llm/` and waits for a matching `.answer.json`).

From a storyboard you wrote yourself (no LLM at all):

```bash
.venv/bin/cutroom render runs/<slug>/storyboard.json
```

Output lands in `runs/<slug>/out/`: one mp4 per format, a contact sheet per format, `qa.json`, `credits.json` and `summary.json`.

Stages are cached. Re-running only redoes what changed. Force a stage with `--force capture,voice,assembly` or `--force all`.

## Tools on their own

```bash
.venv/bin/cutroom tool capture https://example.com --out captures [--mobile]
.venv/bin/cutroom tool stock "mountain lake" [--download assets]
.venv/bin/cutroom tool tts "Hello there." --out hello.wav
.venv/bin/cutroom tool align hello.wav "Hello there."
.venv/bin/cutroom tool render title --params '{"headline":"Hi"}' --seconds 3 --format 9x16 --out title.mp4
.venv/bin/cutroom tool qa runs/<slug>/out/<slug>_16x9.mp4 --format 16x9
```

## Adding a scene template

1. Write `scenes/<name>.html`. Load `lib/base.css`, `lib/runtime.js` and GSAP (or Three.js through the import map).
2. Read inputs from `RS.params`. Build animation with `RS.timeline()` or `RS.onFrame(t => ...)`. Never use timers or `requestAnimationFrame`.
3. Put content inside `.rs-stage` so captions keep their band. Tag text with `data-qa` so QA can check overlaps.
4. Call `RS.start()` at the end.
5. Describe it in `scenes/catalog.json` so the scene designer can pick it.
