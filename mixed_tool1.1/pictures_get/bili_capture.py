import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Tuple

from yt_dlp import YoutubeDL
from imageio_ffmpeg import get_ffmpeg_exe


def normalize_input(s: str) -> str:
    x = s.strip()
    if x.startswith("http://") or x.startswith("https://"):
        return x
    if re.match(r"^(BV[0-9A-Za-z]+)$", x):
        return f"https://www.bilibili.com/video/{x}"
    if re.match(r"^(av[0-9]+)$", x):
        return f"https://www.bilibili.com/video/{x}"
    raise ValueError("输入必须为B站视频链接或BV/av号")


def sanitize_name(name: str) -> str:
    y = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    y = y.strip()
    if not y:
        y = "video"
    return y


def download_video(url: str, work_dir: Path, cookie: str = "") -> Tuple[Path, str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    dl_dir = work_dir / f"dl_{uuid.uuid4().hex[:8]}"
    dl_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare ffmpeg for yt-dlp
    # yt-dlp requires standard 'ffmpeg.exe' name to detect it properly for download_ranges
    ffmpeg_src = get_ffmpeg_exe()
    ffmpeg_bin_dir = work_dir / "ffmpeg_bin"
    ffmpeg_bin_dir.mkdir(exist_ok=True)
    ffmpeg_dest = ffmpeg_bin_dir / "ffmpeg.exe"
    
    if not ffmpeg_dest.exists():
        # Copy without try-except to ensure we know if it fails
        # Verify source exists
        if not os.path.exists(ffmpeg_src):
            raise RuntimeError(f"FFmpeg source not found at {ffmpeg_src}")
        shutil.copy(ffmpeg_src, ffmpeg_dest)
    
    # Add ffmpeg directory to PATH to ensure yt-dlp finds it
    os.environ["PATH"] = str(ffmpeg_bin_dir) + os.pathsep + os.environ["PATH"]

    # Download first 15 seconds only
    def download_range_func(info, ydl):
        return [{'start_time': 0, 'end_time': 15}]

    opts = {
        "outtmpl": str(dl_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        # Optimize: Download video only (no audio), max 720p for faster speed
        "format": "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[ext=mp4]/best",
        "download_ranges": download_range_func,
        "quiet": True,
        "noprogress": True,
        "nocheckcertificate": True,
        # Remove ffmpeg_location and rely on PATH, or point to directory?
        # pointing to exe worked in debug, but PATH is safer fallback
        "ffmpeg_location": str(ffmpeg_dest), 
        "prefer_ffmpeg": True,
        "socket_timeout": 60,
        "retries": 10,
        "fragment_retries": 10,
    }
    ck = (cookie or "").strip()
    if ck:
        opts["http_headers"] = {"Cookie": ck}

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    title = sanitize_name(info.get("title") or "video")
    candidates = list(dl_dir.glob("*.mp4"))
    if not candidates:
        candidates = list(dl_dir.glob("*"))
    if not candidates:
        raise RuntimeError("视频下载失败")
    src = candidates[0]
    target = work_dir / f"{title}.mp4"
    if src != target:
        shutil.move(str(src), str(target))
    shutil.rmtree(dl_dir, ignore_errors=True)
    return target, title


def extract_frames(video_path: Path, out_dir: Path, fps: int = 10, duration_sec: int = 5) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_exe()
    pattern = str(out_dir / "%05d.png")
    cmd = [
        ffmpeg,
        "-y",
        "-t",
        str(duration_sec),
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        pattern,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore"))
    files = list(out_dir.glob("*.png"))
    return len(files)


def process_input(input_text: str, base_output_dir: Path, fps: int = 10, duration_sec: int = 5, cookie: str = "") -> Path:
    url = normalize_input(input_text)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        video_path, title = download_video(url, tmpdir, cookie=cookie)
        video_folder_name = f"{title}"
        target_dir = base_output_dir / video_folder_name
        frames_dir = target_dir / "frames"
        count = extract_frames(video_path, frames_dir, fps=fps, duration_sec=duration_sec)
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(video_path), str(target_dir / video_path.name))
        return frames_dir
