"""encode_gif(): frames -> GIF file, via ffmpeg two-pass palette (quality) or
Pillow (fast, no external binary needed)."""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

ProgressCB = Optional[Callable[[str, float], None]]  # (stage_label, 0..1)


def _resize_frames(frames: list, width: Optional[int]) -> list:
    if not width or width <= 0:
        return frames
    resized = []
    for frame in frames:
        w, h = frame.size
        if w == width:
            resized.append(frame)
            continue
        new_h = max(1, round(h * (width / w)))
        resized.append(frame.resize((width, new_h), Image.LANCZOS))
    return resized


def _find_ffmpeg() -> Optional[str]:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _find_gifsicle() -> Optional[str]:
    return shutil.which("gifsicle")


def encode_gif_ffmpeg(
    frames: list,
    out_path: str,
    fps: int,
    width: Optional[int],
    loop_count: int = 0,
    progress_cb: ProgressCB = None,
) -> None:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    with tempfile.TemporaryDirectory(prefix="gifmaker_") as tmp:
        tmp_path = Path(tmp)
        for i, frame in enumerate(frames):
            frame.convert("RGB").save(tmp_path / f"frame_{i:05d}.png")
            if progress_cb:
                progress_cb("Writing frames", (i + 1) / max(1, len(frames)) * 0.3)

        pattern = str(tmp_path / "frame_%05d.png")
        palette_path = tmp_path / "palette.png"
        scale_filter = f"scale={width}:-1:flags=lanczos" if width else "scale=iw:ih"

        if progress_cb:
            progress_cb("Generating palette", 0.4)
        subprocess.run(
            [
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
                "-vf", f"fps={fps},{scale_filter},palettegen",
                str(palette_path),
            ],
            check=True, capture_output=True,
        )

        if progress_cb:
            progress_cb("Encoding GIF", 0.7)
        subprocess.run(
            [
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern, "-i", str(palette_path),
                "-filter_complex",
                f"fps={fps},{scale_filter}[x];[x][1:v]paletteuse",
                "-loop", str(loop_count),
                str(out_path),
            ],
            check=True, capture_output=True,
        )
        if progress_cb:
            progress_cb("Done", 1.0)


def encode_gif_pillow(
    frames: list,
    out_path: str,
    fps: int,
    width: Optional[int],
    loop_count: int = 0,
    progress_cb: ProgressCB = None,
) -> None:
    if not frames:
        raise ValueError("no frames to export")

    if progress_cb:
        progress_cb("Resizing frames", 0.2)
    resized = [f.convert("P", palette=Image.ADAPTIVE) for f in _resize_frames(frames, width)]

    if progress_cb:
        progress_cb("Encoding GIF", 0.6)
    duration_ms = int(1000 / max(1, fps))
    resized[0].save(
        out_path,
        save_all=True,
        append_images=resized[1:],
        duration=duration_ms,
        loop=loop_count,
        optimize=True,
    )
    if progress_cb:
        progress_cb("Done", 1.0)


def optimize_with_gifsicle(path: str, lossy: int = 30) -> bool:
    """Runs gifsicle -O3 --lossy=N on the file in place, if gifsicle is
    installed. Returns True if optimization ran."""
    gifsicle = _find_gifsicle()
    if not gifsicle:
        return False
    subprocess.run(
        [gifsicle, "-O3", f"--lossy={lossy}", "-o", path, path],
        check=True, capture_output=True,
    )
    return True


def encode_gif(
    frames: list,
    out_path: str,
    fps: int = 15,
    width: Optional[int] = 480,
    loop_count: int = 0,
    quality_mode: str = "quality",
    optimize: bool = False,
    progress_cb: ProgressCB = None,
) -> dict:
    """Encodes frames to a GIF file. quality_mode: "quality" (ffmpeg palette,
    falls back to Pillow if ffmpeg is missing) or "fast" (Pillow only).

    Returns a dict report: {"path", "frame_count", "file_size", "engine"}.
    """
    if not frames:
        raise ValueError("no frames to export")

    engine = "pillow"
    if quality_mode == "quality" and _find_ffmpeg():
        encode_gif_ffmpeg(frames, out_path, fps, width, loop_count, progress_cb)
        engine = "ffmpeg"
    else:
        encode_gif_pillow(frames, out_path, fps, width, loop_count, progress_cb)

    if optimize:
        optimize_with_gifsicle(out_path)

    return {
        "path": out_path,
        "frame_count": len(frames),
        "file_size": Path(out_path).stat().st_size,
        "engine": engine,
    }
