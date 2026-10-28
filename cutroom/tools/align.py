"""Word level timing for a narration clip.

Whisper (via faster-whisper) gives the timing. The script gives the
spelling, so captions never show recognition mistakes. When Whisper is
not installed, words are spread across the clip by length.
"""

from __future__ import annotations

import re
import subprocess
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import numpy as np


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


@lru_cache(maxsize=2)
def _model(size: str):
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8")


def _even(script_words: list[str], duration: float) -> list[dict]:
    weights = [max(2, len(w)) for w in script_words]
    total = sum(weights)
    t, out = 0.0, []
    for w, wt in zip(script_words, weights):
        d = duration * wt / total
        out.append({"w": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def align(wav: Path, script: str, duration: float, model_size: str = "base.en", language: str = "en") -> dict:
    """Return {"words": [{w, start, end}], "method": "whisper" | "even"}."""
    script_words = script.split()
    try:
        model = _model(model_size if language == "en" else model_size.replace(".en", ""))
    except ImportError:
        return {"words": _even(script_words, duration), "method": "even"}

    # Decode with ffmpeg ourselves. faster-whisper's own decoder breaks on newer PyAV releases.
    pcm = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    segments, _ = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=False)
    heard = [w for seg in segments for w in (seg.words or [])]
    if not heard:
        return {"words": _even(script_words, duration), "method": "even"}

    # Map each script word to the Whisper word that matches it.
    a = [_norm(w) for w in script_words]
    b = [_norm(w.word) for w in heard]
    timed: list[dict | None] = [None] * len(script_words)
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            h = heard[blk.b + k]
            timed[blk.a + k] = {"w": script_words[blk.a + k], "start": round(float(h.start), 3), "end": round(float(h.end), 3)}

    # Fill unmatched words by interpolating between their timed neighbours.
    i = 0
    while i < len(timed):
        if timed[i] is not None:
            i += 1
            continue
        j = i
        while j < len(timed) and timed[j] is None:
            j += 1
        lo = timed[i - 1]["end"] if i > 0 else 0.0
        hi = timed[j]["start"] if j < len(timed) else duration
        step = max(hi - lo, 0.05 * (j - i)) / (j - i)
        for k in range(i, j):
            s = lo + step * (k - i)
            timed[k] = {"w": script_words[k], "start": round(s, 3), "end": round(s + step, 3)}
        i = j
    return {"words": timed, "method": "whisper"}
