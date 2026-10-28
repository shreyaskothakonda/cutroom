"""ffmpeg assembly: voice track, scene concat, mux and loudness."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def voice_track(clips: list[dict], out_wav: Path, sample_rate: int = 48000) -> str:
    """Lay each clip at its scene offset. clips: [{wav, offset, duration}], duration is the scene length."""
    total = sum(c["duration"] for c in clips)
    inputs, chains = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", c["wav"]]
        ms = int(round(c["offset"] * 1000))
        chains.append(f"[{i}:a]aresample={sample_rate},aformat=channel_layouts=mono,adelay={ms}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(clips)))
    graph = ";".join(chains) + f";{mix}amix=inputs={len(clips)}:normalize=0,apad,atrim=0:{total:.3f}[out]"
    _run([*inputs, "-filter_complex", graph, "-map", "[out]", "-ar", str(sample_rate), str(out_wav)])
    return str(out_wav)


def concat(videos: list[Path], out_mp4: Path) -> str:
    """Join silent scene renders. They share codec settings, so stream copy is safe."""
    lst = Path(out_mp4).with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(v).resolve()}'\n" for v in videos))
    _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_mp4)])
    lst.unlink()
    return str(out_mp4)


def mux(video: Path, audio: Path, out_mp4: Path, music: Path | None = None) -> str:
    """Add the voice track, normalised to -16 LUFS (web and social standard)."""
    if music:
        graph = ("[1:a]asplit[v1][v2];[2:a]volume=0.12[m];[m][v1]sidechaincompress=threshold=0.05:ratio=8[duck];"
                 "[v2][duck]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
        extra = ["-stream_loop", "-1", "-i", str(music)]
    else:
        graph, extra = "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]", []
    _run([
        "-i", str(video), "-i", str(audio), *extra,
        "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
        "-movflags", "+faststart", str(out_mp4),
    ])
    return str(out_mp4)


def poster(video: Path, out_jpg: Path, at: float) -> str:
    _run(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out_jpg)])
    return str(out_jpg)


def contact_sheet(video: Path, out_png: Path, cols: int = 5, rows: int = 2) -> str:
    """One image of evenly spaced frames, for a quick look."""
    dur = probe_duration(video)
    n = cols * rows
    fps = n / max(dur, 0.1)
    _run(["-i", str(video), "-vf", f"fps={fps:.4f},scale=480:-2,tile={cols}x{rows}:padding=6:color=white",
          "-frames:v", "1", str(out_png)])
    return str(out_png)
