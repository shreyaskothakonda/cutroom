"""Text to speech with free, local voices.

Engines:
  kokoro      default. Open weights, fast on CPU, many English voices.
  say         macOS built-in. Last resort when Kokoro is not installed.
  chatterbox  voice cloning (phase 2).
  indic       Indic Parler TTS or IndicF5 for Indian languages (phase 2).

All engines write a 24 kHz mono WAV and return its duration.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

SAMPLE_RATE = 24000


@lru_cache(maxsize=4)
def _kokoro_pipeline(lang_code: str):
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")


def _kokoro(text: str, out_wav: Path, voice: str, speed: float) -> None:
    import numpy as np
    import soundfile as sf

    # Kokoro voice names start with the language code: af_heart -> "a".
    pipeline = _kokoro_pipeline(voice[0])
    chunks = [audio for _, _, audio in pipeline(text, voice=voice, speed=speed)]
    audio = np.concatenate([np.asarray(c) for c in chunks])
    sf.write(str(out_wav), audio, SAMPLE_RATE)


def _say(text: str, out_wav: Path, voice: str, speed: float) -> None:
    aiff = out_wav.with_suffix(".aiff")
    cmd = ["say", "-o", str(aiff), "-r", str(int(185 * speed))]
    if voice and "_" not in voice:  # Kokoro names like af_heart mean nothing to say
        cmd += ["-v", voice]
    subprocess.run(cmd + [text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", str(SAMPLE_RATE), "-ac", "1", str(out_wav)],
        check=True,
    )
    aiff.unlink()


def _not_yet(name: str, hint: str):
    def engine(*_a, **_k):
        raise NotImplementedError(f"The {name} engine is planned for phase 2. {hint}")

    return engine


ENGINES = {
    "kokoro": _kokoro,
    "say": _say,
    "chatterbox": _not_yet("chatterbox", "Install chatterbox-tts and pass a reference clip."),
    "indic": _not_yet("indic", "Install parler-tts (Indic Parler) or IndicF5."),
}


def available_engine(preferred: str = "kokoro") -> str:
    if preferred == "kokoro":
        try:
            import kokoro  # noqa: F401

            return "kokoro"
        except ImportError:
            pass
        if shutil.which("say"):
            return "say"
        raise RuntimeError("No TTS engine found. Install the voice extras: uv pip install -e '.[voice]'")
    return preferred


def wav_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def speak(text: str, out_wav: Path, engine: str = "kokoro", voice: str = "af_heart", speed: float = 1.0) -> dict:
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    engine = available_engine(engine)
    ENGINES[engine](text, out_wav, voice, speed)
    return {"wav": str(out_wav), "duration": wav_duration(out_wav), "engine": engine, "voice": voice}
