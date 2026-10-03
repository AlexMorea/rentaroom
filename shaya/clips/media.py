"""Video probing and the 'data saver' transcode.

Data in South Africa is expensive, so every clip also gets a ~480p,
low-bitrate copy that the feed serves by default. In production this runs
in a background worker (or a managed service like Cloudflare Stream / Mux);
the MVP runs it inline when ffmpeg is installed and skips it otherwise.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File


def ffmpeg_available():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe_duration(path):
    """Return the clip length in seconds, or None if it can't be read."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
            capture_output=True,
            timeout=30,
            check=True,
        ).stdout
        return float(json.loads(out)["format"]["duration"])
    except (subprocess.SubprocessError, KeyError, ValueError):
        return None


def make_data_saver_copy(video):
    if not (settings.SHAYA["TRANSCODE_DATA_SAVER"] and ffmpeg_available()):
        return False
    src = Path(video.file.path)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{src.stem}-lite.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-vf", "scale=-2:'min(480,ih)'",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                    "-maxrate", "600k", "-bufsize", "1200k",
                    "-c:a", "aac", "-b:a", "64k", "-ac", "1",
                    "-movflags", "+faststart",
                    str(out),
                ],
                check=True,
                timeout=300,
            )
        except subprocess.SubprocessError:
            return False
        with out.open("rb") as fh:
            video.data_saver_file.save(out.name, File(fh), save=True)
    return True
