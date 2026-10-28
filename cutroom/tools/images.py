"""Image prep with Pillow: normalise, resize, crop and pad."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def normalise(src: Path, out: Path | None = None, max_side: int = 2800) -> dict:
    """Fix EXIF rotation, convert to RGB JPEG, cap the long side."""
    src = Path(src)
    out = Path(out) if out else src.with_name(src.stem + "_n.jpg")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(out, "JPEG", quality=92)
        return {"path": str(out), "width": im.width, "height": im.height}


def cover(src: Path, out: Path, width: int, height: int, focus: tuple[float, float] = (0.5, 0.5)) -> str:
    """Crop to fill width x height around a focus point (0..1, 0..1)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        scale = max(width / im.width, height / im.height)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        left = min(max(0, round(im.width * focus[0] - width / 2)), im.width - width)
        top = min(max(0, round(im.height * focus[1] - height / 2)), im.height - height)
        im.crop((left, top, left + width, top + height)).save(out, quality=92)
    return str(out)


def contain(src: Path, out: Path, width: int, height: int, bg: str = "#0b0d12") -> str:
    """Fit inside width x height and pad with a flat colour."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        ImageOps.pad(im, (width, height), color=bg).save(out, quality=92)
    return str(out)
