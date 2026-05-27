#!/usr/bin/env python3
"""
B5 - Video Creation (ASS Premium - Ultra Fast + Beautiful Effects)
Uses FFmpeg and ASS subtitles with Premium effects (Fade, Glow, Shadow).

Example usage:
python B5-Create-Video/create_video_ass.py --content-name content1 --output-types 9_16,16_9
"""

import os
import sys
import random
import re
import argparse
import subprocess
import shutil
import time
import wave
import contextlib

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# =================================================================
# CẤU HÌNH TÙY CHỈNH (CONFIGURATIONS)
# =================================================================
DEFAULT_FPS = 30

# ASS Style Configuration (Glow & Premium Look)
# Font: Archivo Black, Size: 80
# PrimaryColour: &H00FFFFFF (White)
# OutlineColour: &H00000000 (Black)
# BackColour: &H80000000 (Shadow)
# Spacing: 2 (Character spacing)
# BorderStyle: 1 (Outline + DropShadow)
# Outline: 3 (Thick border)
# Shadow: 5 (Deep shadow)
# Alignment: 2 (Bottom Center)
ASS_STYLE = "Style: Default,Archivo Black,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,3,5,2,10,10,60,1"

# 9:16 (Portrait) Style - Video on top, subtitles at bottom
# Font: Calibri, Size: 65
# Alignment: 8 (Top Center) - anchors subtitles from top, wraps if long
# MarginV: 980 = position just below main video frame (ends ~y=936)
ASS_STYLE_9_16 = "Style: Default,Calibri,65,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,3,5,8,10,10,980,1"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "B2-TTS", "export")
SRT_DIR = os.path.join(BASE_DIR, "B4-Verify-SRT", "export")
VIDEO_LIBRARY = os.path.join(BASE_DIR, "B5-Create-Video", "Library")
OUTPUT_DIR = os.path.join(BASE_DIR, "B5-Create-Video", "export")
TMP_DIR = os.path.join(BASE_DIR, "B5-Create-Video", "tmp_ass")

def log(msg: str):
    print(f"[B5-ASS] {msg}")

def get_wav_duration_seconds(wav_path: str) -> float:
    with contextlib.closing(wave.open(wav_path, "rb")) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if not rate:
            return 0.0
        return float(frames) / float(rate)

def ffprobe_duration_seconds(video_path: str):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            video_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur = float((r.stdout or "").strip() or 0.0)
        if dur <= 0:
            return None
        return dur
    except Exception:
        return None

def pick_random_playlist(video_files, target_duration: float):
    if not video_files:
        raise RuntimeError("Library is empty, no videos available.")
    playlist = []
    remaining = max(0.0, float(target_duration))
    tries = 0
    while remaining > 0 and tries < 500 and len(playlist) < 80:
        tries += 1
        p = random.choice(video_files)
        d = ffprobe_duration_seconds(p)
        if not d:
            continue
        seg = min(d, remaining + 0.75)
        playlist.append({"path": p, "duration": seg})
        remaining -= seg
    if remaining > 0:
        raise RuntimeError("Not enough valid videos in Library to match audio duration.")
    return playlist

def build_filter_complex_for_playlist(playlist, ass_path_fixed: str, out_w: int, out_h: int, overlay_y: str = "(H-h)/2"):
    parts = []
    vlabels = []
    for i, item in enumerate(playlist):
        d = float(item["duration"])
        parts.append(
            f"[{i}:v]trim=duration={d:.6f},setpts=PTS-STARTPTS,split=2[v{i}a][v{i}b];"
            f"[v{i}a]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},boxblur=20:1[bg{i}];"
            f"[v{i}b]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg{i}];"
            f"[bg{i}][fg{i}]overlay=(W-w)/2:{overlay_y}:shortest=1,fps={DEFAULT_FPS},format=yuv420p,setsar=1[v{i}];"
        )
        vlabels.append(f"[v{i}]")

    parts.append(f"{''.join(vlabels)}concat=n={len(playlist)}:v=1:a=0[base];")
    parts.append(f"[base]ass='{ass_path_fixed}',fps={DEFAULT_FPS},format=yuv420p,setsar=1[v]")
    return "".join(parts), "[v]"

def srt_time_to_ass(srt_time):
    # srt: 00:00:00,000 -> ass: 0:00:00.00
    h, m, s, ms = re.split('[:,]', srt_time)
    return f"{int(h)}:{m}:{s}.{int(ms)//10:02d}"

def generate_ass(srt_path, ass_path, play_res_x: int, play_res_y: int, ass_style: str = ASS_STYLE):
    if not os.path.exists(srt_path): return False
    
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    # Normalize line endings and split by block number (standalone number at start of line)
    content = content.replace('\r\n', '\n')
    # Regex split by block number: number at start of line, followed by line containing timestamp
    blocks = re.split(r'\n(?=\d+\n\d{2}:\d{2}:\d{2})', '\n' + content)
    blocks = [b.strip() for b in blocks if b.strip()]
    
    log(f"Found {len(blocks)} blocks in SRT file.")
    
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{ass_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2: continue
        
        # Find time line in block
        time_line = ""
        text_lines = []
        for line in lines:
            if "-->" in line:
                time_line = line
            elif line.strip() and not line.strip().isdigit():
                text_lines.append(line.strip())
        
        if not time_line or not text_lines: continue
        
        time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
        if not time_match: continue
        
        start_ass = srt_time_to_ass(time_match.group(1))
        end_ass = srt_time_to_ass(time_match.group(2))
        
        text = " ".join(text_lines).upper()
        rich_text = f"{{\\fad(200,200)}}{text}"
        
        events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{rich_text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events))
    return True

def main():
    parser = argparse.ArgumentParser(description="B5 - ASS Premium Video")
    parser.add_argument("--content-name", default="content1", help="Content file name")
    parser.add_argument("--output-types", default="9_16,16_9", help="List of output types: 9_16,16_9")
    args = parser.parse_args()

    content_output_dir = os.path.join(OUTPUT_DIR, args.content_name)
    os.makedirs(content_output_dir, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    audio_file = os.path.join(AUDIO_DIR, f"{args.content_name}_output_audio.wav")
    srt_file = os.path.join(SRT_DIR, f"{args.content_name}_subtitles_verified.srt")

    if not (os.path.exists(audio_file) and os.path.exists(srt_file)):
        log("[ERROR] Missing input files.")
        sys.exit(1)

    video_files = [os.path.join(VIDEO_LIBRARY, f) for f in os.listdir(VIDEO_LIBRARY) if f.lower().endswith(('.mp4', '.mov'))]
    audio_duration = get_wav_duration_seconds(audio_file)
    output_types = [t.strip() for t in (args.output_types or "").split(",") if t.strip()]
    variants = {"9_16": (1080, 1920), "16_9": (1920, 1080)}
    total_start = time.time()
    try:
        for t in output_types:
            if t not in variants:
                log(f"Skipping unsupported output type: {t}")
                continue

            out_w, out_h = variants[t]
            ass_file = os.path.join(TMP_DIR, f"{args.content_name}_{t}.ass")
            output_video = os.path.join(content_output_dir, f"{args.content_name}_ass_{t}.mp4")

            # Adjust video and subtitle position based on aspect ratio
            if t == "9_16":
                # 9:16 - Video pushed to top, subtitles anchored below video frame
                overlay_y = "(H-h)/4"
                # Use ASS style with Alignment=8 (Top Center), subtitles always start at same height
                ass_style = ASS_STYLE_9_16
            else:
                # 16:9 (Landscape) - Keep centered
                overlay_y = "(H-h)/2"
                ass_style = ASS_STYLE

            log(f"Generating ASS Premium subtitle file from {srt_file}...")
            if not generate_ass(srt_file, ass_file, out_w, out_h, ass_style):
                log("[ERROR] Cannot create ASS file.")
                sys.exit(1)

            log(f" ✓ ASS file created at: {ass_file}")

            ass_path_fixed = ass_file.replace("\\", "/").replace(":", "\\:")
            playlist = pick_random_playlist(video_files, audio_duration)
            filter_complex, vmap = build_filter_complex_for_playlist(playlist, ass_path_fixed, out_w, out_h, overlay_y)

            log(f"Rendering video with FFmpeg ({t}, random {len(playlist)} clips from Library)...")
            ffmpeg_cmd = ["ffmpeg", "-y", "-loglevel", "info"]
            for item in playlist:
                ffmpeg_cmd += ["-i", item["path"]]
            ffmpeg_cmd += ["-i", audio_file]
            ffmpeg_cmd += [
                "-filter_complex",
                filter_complex,
                "-map",
                vmap,
                "-map",
                f"{len(playlist)}:a",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                output_video,
            ]

            start_time = time.time()
            subprocess.run(ffmpeg_cmd, check=True)
            elapsed = time.time() - start_time
            log(f" ✓ COMPLETED: {output_video}")
            log(f" ✓ Render time: {elapsed:.2f} seconds.")
    finally:
        log(f"Total time: {time.time() - total_start:.2f}s")

    # Temporarily keep TMP_DIR for ASS file inspection
    # if os.path.exists(TMP_DIR): shutil.rmtree(TMP_DIR)

if __name__ == "__main__":
    main()
