# Cutroom

## Goal

Turn a short brief into a finished, narrated video in 16:9 and 9:16.

A team of agents plans the video. Local tools do the real work. The LLM only plans and writes. Everything that can be done without tokens is done by a Python tool: browser capture, rendering, voice, timing, stock search, assembly and QA.

Free tools by default. No paid API is needed to make a video.

## Agent roles

| Agent | Uses an LLM | Job |
|---|---|---|
| Planner | yes | Reads the brief. Picks the angle, audience, length and scene list. |
| Scriptwriter | yes | Writes the narration for each scene. Short sentences, spoken style. |
| Scene designer | yes | Picks a scene template per scene, fills its params, asks for assets (captures, stock). |
| Capture | no | Runs the capture and stock tools. Writes asset paths into the storyboard. |
| Voice | no | Speaks each scene, then aligns words to time with Whisper. |
| Assembly | no | Renders every scene frame by frame, joins them, adds the voice track. |
| QA | no | Checks blank frames, frozen video, silence, A/V drift and text overlap. |

The three LLM agents write one shared file, `storyboard.json`. The four tool agents read it. A storyboard can also be written by hand and run with no LLM at all.

## Tools (all local, all free)

| Tool | What it does | Built on |
|---|---|---|
| `capture` | Full page and viewport screenshots of real sites | Playwright (headless Chromium) |
| `render` | Renders an HTML scene to video, frame by frame | Playwright, GSAP, Three.js, ffmpeg |
| `tts` | Text to speech | Kokoro (default). Chatterbox for cloning, Indic Parler or IndicF5 for Indian languages (phase 2). macOS `say` as a last resort |
| `align` | Word level timestamps | faster-whisper |
| `stock` | Search and download CC media with credits | Openverse, Wikimedia Commons (no key). Pexels, Pixabay (free key) |
| `images` | Resize, crop, pad for each format | Pillow |
| `assemble` | Concat scenes, build the voice track, mux, loudness | ffmpeg |
| `qa` | Blank and frozen frames, silence, durations, overlap | ffmpeg filters, numpy |

Every tool is a plain function and also a CLI command: `cutroom tool <name> ...`.

## Architecture

```
brief.yaml
   │
   ▼
Planner ─► Scriptwriter ─► Scene designer        (LLM, writes JSON)
   │
   ▼
storyboard.json
   │
   ▼
Capture ─► Voice ─► Assembly ─► QA               (tools, no tokens)
   │
   ▼
runs/<slug>/out/<slug>_16x9.mp4, <slug>_9x16.mp4, qa.json, credits.json
```

**Scenes are HTML pages.** Each one loads a small runtime (`scenes/lib/runtime.js`) and exposes `renderFrame(t)`. GSAP timelines are paused and seeked. Three.js renders on demand. The renderer steps time frame by frame and screenshots, so output is exact and repeatable, with no dropped frames.

**Captions are part of the scene.** The runtime draws word-timed captions from the Whisper output. The same runtime reports the boxes of every labelled element, so QA can catch overlaps.

**Layout adapts to the format.** Templates read `--w` and `--h` and a `portrait` or `landscape` class. One storyboard renders both 16:9 and 9:16.

**LLM backends.** `claude-cli` (default, uses the local Claude Code login), `anthropic` (API key), or `manual` (writes the prompt to a file and waits for an answer file). A storyboard can skip the LLM entirely.

**Runs are cached.** Each stage writes its output into `runs/<slug>/`. Re-running skips finished work unless you pass `--force`.

## Phase 1 scope

- Brief to storyboard with the three LLM agents.
- Scene templates: `title`, `website` (real capture, scrolling browser), `photo` (stock image, Ken Burns), `orb3d` (Three.js), `bullets`, `outro`.
- Kokoro voice in English, Whisper word timing, burned-in captions.
- Openverse and Wikimedia stock images with a credits file.
- 16:9 and 9:16 output at 30 fps.
- QA report with pass or fail.

## Later phases

- Phase 2: Chatterbox voice cloning, Indic Parler and IndicF5, stock video from Pexels and Pixabay, background music with ducking, recorded browser interactions (clicks, typing).
- Phase 3: QA feedback loop back to the scene designer, more templates, brand kits, a small web UI.
