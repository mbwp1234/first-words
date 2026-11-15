"""Cut a saved video on the server with ffmpeg (shipped in the Home Assistant image).

The cut is re-encoded to H.264 + AAC in an .mp4, which every browser can play;
iPhone originals are often HEVC with PCM sound (Live Photos), which desktop
browsers show without sound. If this ffmpeg has no H.264 encoder, the cut is a
stream copy into .mov instead (exact, but keyframe-aligned and no more playable
than the original). The original file is never touched.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

TIMEOUT_S = 600
PAD_S = 0.0

_encoders: set[str] | None = None


def ffmpeg_binary() -> str | None:
    return os.environ.get("FW_FFMPEG") or shutil.which("ffmpeg")


async def _run(*args: str, timeout: float = TIMEOUT_S) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out or b""


async def _has_encoder(ff: str, name: str) -> bool:
    global _encoders
    if _encoders is None:
        code, out = await _run(ff, "-hide_banner", "-encoders", timeout=30)
        _encoders = set()
        if code == 0:
            for line in out.decode(errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 2 and len(parts[0]) == 6:
                    _encoders.add(parts[1])
    return name in _encoders


class TrimFailed(Exception):
    pass


async def cut(src: Path, dst: Path, start: float, end: float) -> str:
    """Cut [start, end] of src into dst (its suffix may change). Returns the extension used."""
    ff = ffmpeg_binary()
    if not ff:
        raise TrimFailed("Home Assistant has no ffmpeg, so it can't trim videos.")
    dur = max(0.5, end - start)
    if await _has_encoder(ff, "libx264"):
        out = dst.with_suffix(".mp4")
        args = [ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                # main picture + first sound track; a Live Photo carries extra small video and data tracks
                "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", "-f", "mp4", str(out)]
        ext = "mp4"
    else:
        out = dst.with_suffix(".mov")
        args = [ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "mov", str(out)]
        ext = "mov"
    try:
        code, log = await _run(*args)
    except asyncio.TimeoutError as err:
        raise TrimFailed("Trimming took too long and was stopped.") from err
    if code != 0 or not out.exists() or out.stat().st_size == 0:
        tail = log.decode(errors="replace").strip().splitlines()[-1:] or ["no output"]
        raise TrimFailed(f"ffmpeg couldn't trim this video ({tail[0][:200]}).")
    return ext
