#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AudioBackground - Thêm nhạc nền vào video với âm lượng tuỳ chỉnh
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import sys
import threading
import re
import json
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── Configuration ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
TEMP_DIR = BASE_DIR / "temp"
FFMPEG_CMD = "ffmpeg"

# ─── Utility Functions ───────────────────────────────────────────────────────

def get_file_duration(file_path):
    """Get duration of media file in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0


def video_has_audio(file_path):
    """Check if a video file has an audio stream using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=nokey=1:noprint_wrappers=1",
            str(file_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and "audio" in result.stdout.strip()
    except Exception:
        return True  # Assume has audio if we can't check


def format_duration(seconds):
    """Format seconds to MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_size(size_bytes):
    """Format bytes to human readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def check_ffmpeg():
    """Check if ffmpeg is available."""
    try:
        result = subprocess.run(
            [FFMPEG_CMD, "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ─── Color Palette (Catppuccin Latte - Light) ─────────────────────────────────

class Colors:
    BG = "#eff1f5"        # Nền chính - trắng kem nhẹ
    BG2 = "#e6e9ef"       # Nền phụ (frame) - xám nhạt
    BG3 = "#ccd0da"        # Nền input/entry - xám đậm hơn
    FG = "#4c4f69"         # Chữ chính - xám đậm
    FG2 = "#6c6f85"        # Chữ phụ - xám vừa
    ACCENT = "#1e66f5"     # Xanh dương accent
    ACCENT2 = "#2a7cf6"    # Xanh dương hover
    SUCCESS = "#40a02b"    # Xanh lá (export)
    SUCCESS2 = "#34911f"   # Xanh lá hover
    ERROR = "#d20f39"      # Đỏ
    WARNING = "#df8e1d"    # Vàng cam
    BORDER = "#bcc0cc"     # Viền
    TROUGH = "#ccd0da"     # Màu nền slider trough
    SLIDER_ACTIVE = "#1e66f5"  # Slider active
    WHITE = "#ffffff"       # Trắng (chữ trên button màu)


# ─── Main Application ───────────────────────────────────────────────────────

class AudioBackgroundApp:
    """GUI application for adding background audio to video."""

    def __init__(self, root):
        self.root = root
        self.root.title("AudioBackground - Thêm nhạc nền vào video")
        self.root.geometry("780x740")
        self.root.configure(bg=Colors.BG)
        self.root.resizable(False, False)
        self.root.minsize(780, 740)

        # ── State Variables ──
        self.video_path = tk.StringVar()
        self.audio_path = tk.StringVar()
        self.volume = tk.DoubleVar(value=50.0)  # Âm lượng nhạc nền 0-200%
        self.video_volume = tk.DoubleVar(value=100.0)  # Âm lượng video gốc 0-200%
        self.loop_audio = tk.BooleanVar(value=False)  # Loop nhạc nền
        self.video_info_text = tk.StringVar(value="Chưa chọn video")
        self.audio_info_text = tk.StringVar(value="Chưa chọn audio")
        self.status_text = tk.StringVar(value="Sẵn sàng")
        self.progress_value = tk.DoubleVar(value=0.0)
        self.preview_file = tk.StringVar(value="")

        self.is_processing = False
        self.ffmpeg_process = None
        self.should_cancel = False

        # Tạo thư mục tạm
        TEMP_DIR.mkdir(exist_ok=True)

        # Kiểm tra ffmpeg
        if not check_ffmpeg():
            messagebox.showerror(
                "Thiếu FFmpeg",
                "Không tìm thấy FFmpeg! Vui lòng cài đặt FFmpeg và thêm vào PATH.\n\n"
                "Tải tại: https://ffmpeg.org/download.html"
            )

        self._build_ui()
        self._apply_styles()
        self._load_config()

        # Xử lý đóng cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Building ──────────────────────────────────────────────────────────

    def _apply_styles(self):
        """Apply ttk styles for a consistent look."""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "TProgressbar",
            background=Colors.ACCENT,
            troughcolor=Colors.TROUGH,
            bordercolor=Colors.BORDER,
            lightcolor=Colors.ACCENT,
            darkcolor=Colors.ACCENT,
        )
        style.configure(
            "TLabel",
            background=Colors.BG,
            foreground=Colors.FG,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=Colors.BG,
            foreground=Colors.FG,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Sub.TLabel",
            background=Colors.BG,
            foreground=Colors.FG2,
            font=("Segoe UI", 10),
        )

    def _build_ui(self):
        """Build the entire UI layout."""
        # ── Main container ──
        main = tk.Frame(self.root, bg=Colors.BG)
        main.pack(fill="both", expand=True, padx=24, pady=20)

        # ═══════════════════ HEADER ═══════════════════
        header = tk.Frame(main, bg=Colors.BG)
        header.pack(fill="x", pady=(0, 16))

        title_row = tk.Frame(header, bg=Colors.BG)
        title_row.pack(fill="x")

        tk.Label(
            title_row, text="🎵  AudioBackground",
            font=("Segoe UI", 20, "bold"),
            bg=Colors.BG, fg=Colors.FG,
        ).pack(side="left")

        tk.Label(
            title_row, text="v1.0",
            font=("Segoe UI", 9),
            bg=Colors.BG, fg=Colors.FG2,
        ).pack(side="left", padx=(8, 0), pady=(8, 0))

        tk.Label(
            header, text="Thêm nhạc nền vào video — âm lượng tuỳ chỉnh, nghe thử trước khi xuất",
            font=("Segoe UI", 10),
            bg=Colors.BG, fg=Colors.FG2,
            anchor="w",
        ).pack(fill="x")

        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=(0, 16))

        # ═══════════════════ INPUT FILES ═══════════════════
        files_frame = self._make_card(main, "  📁  File đầu vào  ", pady_bottom=14)

        # -- Video row --
        self._add_file_row(
            files_frame, "🎬  Video:", self.video_path,
            self.video_info_text, self._select_video
        )

        # -- Audio row --
        self._add_file_row(
            files_frame, "🎵  Audio:", self.audio_path,
            self.audio_info_text, self._select_audio
        )

        # ═══════════════════ BACKGROUND AUDIO VOLUME ═══════════════════
        bgm_frame = self._make_card(main, "  🎵  Âm lượng nhạc nền  ", pady_bottom=14)
        self._add_volume_slider(
            bgm_frame, self.volume, self._on_bgm_volume_change,
            "Nhẹ (20%)", 20, "Vừa (50%)", 50, "Rõ (100%)", 100, "Mạnh (150%)", 150
        )

        # Loop checkbox
        loop_row = tk.Frame(bgm_frame, bg=Colors.BG2)
        loop_row.pack(fill="x", pady=(6, 0))

        self.loop_checkbox = tk.Checkbutton(
            loop_row, text="🔁  Loop nhạc nền (tự động lặp nếu audio ngắn hơn video)",
            variable=self.loop_audio,
            font=("Segoe UI", 9),
            bg=Colors.BG2, fg=Colors.FG,
            selectcolor=Colors.BG3,
            activebackground=Colors.BG2, activeforeground=Colors.FG,
            highlightthickness=0,
            relief="flat",
            cursor="hand2",
        )
        self.loop_checkbox.pack(side="left")

        # ═══════════════════ VIDEO ORIGINAL VOLUME ═══════════════════
        video_vol_frame = self._make_card(main, "  🎬  Âm lượng video gốc  ", pady_bottom=14)
        self._add_volume_slider(
            video_vol_frame, self.video_volume, self._on_video_volume_change,
            "Tắt (0%)", 0, "Nhẹ (50%)", 50, "Giữ nguyên (100%)", 100, "Mạnh (150%)", 150
        )

        # ═══════════════════ ACTION BUTTONS ═══════════════════
        actions = tk.Frame(main, bg=Colors.BG)
        actions.pack(fill="x", pady=(0, 14))

        # Preview
        self.btn_preview = tk.Button(
            actions, text="▶  Nghe thử (15s)",
            font=("Segoe UI", 11, "bold"),
            bg=Colors.ACCENT, fg=Colors.WHITE,
            relief="flat", bd=0,
            padx=22, pady=10,
            cursor="hand2",
            activebackground=Colors.ACCENT2,
            command=self._preview,
        )
        self.btn_preview.pack(side="left", padx=(0, 10))

        # Export
        self.btn_export = tk.Button(
            actions, text="💾  Xuất video",
            font=("Segoe UI", 11, "bold"),
            bg=Colors.SUCCESS, fg=Colors.WHITE,
            relief="flat", bd=0,
            padx=22, pady=10,
            cursor="hand2",
            activebackground=Colors.SUCCESS2,
            command=self._export,
        )
        self.btn_export.pack(side="left")

        # Cancel
        self.btn_cancel = tk.Button(
            actions, text="✕  Huỷ",
            font=("Segoe UI", 10),
            bg=Colors.ERROR, fg=Colors.WHITE,
            relief="flat", bd=0,
            padx=14, pady=10,
            cursor="hand2",
            state="disabled",
            activebackground="#e07a8f",
            command=self._cancel_operation,
        )
        self.btn_cancel.pack(side="right")

        # ═══════════════════ STATUS & PROGRESS ═══════════════════
        status_frame = tk.Frame(main, bg=Colors.BG)
        status_frame.pack(fill="x")

        # Status bar
        status_bar = tk.Frame(
            status_frame, bg=Colors.BG3,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
            bd=0,
        )
        status_bar.pack(fill="x", ipady=2)

        self.status_icon = tk.Label(
            status_bar, text="  ●",
            font=("Segoe UI", 10),
            bg=Colors.BG3, fg=Colors.SUCCESS,
        )
        self.status_icon.pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(
            status_bar, textvariable=self.status_text,
            font=("Segoe UI", 9),
            bg=Colors.BG3, fg=Colors.FG,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(6, 8), pady=4)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            status_frame,
            orient="horizontal",
            variable=self.progress_value,
            mode="determinate",
            length=740,
        )
        self.progress_bar.pack(fill="x", pady=(6, 0))

    def _make_card(self, parent, title, pady_bottom=12):
        """Create a labeled card/frame with border."""
        frame = tk.LabelFrame(
            parent, text=title,
            font=("Segoe UI", 10, "bold"),
            bg=Colors.BG2, fg=Colors.FG,
            padx=16, pady=14,
            relief="flat", bd=0,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
        )
        frame.pack(fill="x", pady=(0, pady_bottom))
        return frame

    def _add_file_row(self, parent, label_text, path_var, info_var, select_cmd):
        """Add a file selection row with label, entry, info, and button."""
        row = tk.Frame(parent, bg=Colors.BG2)
        row.pack(fill="x", pady=(0, 10))

        # Label
        tk.Label(
            row, text=label_text,
            font=("Segoe UI", 10),
            bg=Colors.BG2, fg=Colors.FG,
            width=9, anchor="w",
        ).pack(side="left")

        # Entry with full path
        entry = tk.Entry(
            row, textvariable=path_var,
            font=("Segoe UI", 9),
            bg=Colors.BG3, fg=Colors.FG,
            relief="flat", bd=0,
            insertbackground=Colors.FG,
            readonlybackground=Colors.BG3,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))

        # Browse button
        btn = tk.Button(
            row, text="Chọn file",
            font=("Segoe UI", 9),
            bg=Colors.ACCENT, fg=Colors.WHITE,
            relief="flat", bd=0,
            padx=14, pady=4,
            cursor="hand2",
            activebackground=Colors.ACCENT2,
            command=select_cmd,
        )
        btn.pack(side="right")

        # Info row
        info_row = tk.Frame(parent, bg=Colors.BG2)
        info_row.pack(fill="x", padx=(76, 0))

        info_label = tk.Label(
            info_row, textvariable=info_var,
            font=("Segoe UI", 8),
            bg=Colors.BG2, fg=Colors.FG2,
            anchor="w",
        )
        info_label.pack(fill="x", pady=(2, 0) if "Audio" in label_text else (0, 2))

        # Store reference
        if "Video" in label_text:
            self.video_entry = entry
            self.video_info_label = info_label
            self.btn_video = btn
        elif "Audio" in label_text:
            self.audio_entry = entry
            self.audio_info_label = info_label
            self.btn_audio = btn

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _add_volume_slider(self, parent, var, callback, *presets):
        """Add a volume slider with value display, indicators, and preset buttons."""
        control = tk.Frame(parent, bg=Colors.BG2)
        control.pack(fill="x", pady=(4, 0))

        slider_frame = tk.Frame(control, bg=Colors.BG2)
        slider_frame.pack(fill="x", expand=True)

        slider = tk.Scale(
            slider_frame,
            from_=0, to=200,
            orient="horizontal",
            variable=var,
            bg=Colors.BG2, fg=Colors.FG,
            troughcolor=Colors.TROUGH,
            activebackground=Colors.SLIDER_ACTIVE,
            highlightbackground=Colors.BG2,
            sliderrelief="flat",
            length=420,
            showvalue=False,
            font=("Segoe UI", 9),
            command=callback,
        )
        slider.pack(side="left", fill="x", expand=True, padx=(0, 16))

        # Value display
        val_frame = tk.Frame(control, bg=Colors.BG2)
        val_frame.pack(side="left")

        label = tk.Label(
            val_frame,
            text=f"{int(var.get())}%",
            font=("Segoe UI", 14, "bold"),
            bg=Colors.BG2, fg=Colors.ACCENT,
            width=5,
        )
        label.pack()

        tk.Label(
            val_frame,
            text="âm lượng",
            font=("Segoe UI", 8),
            bg=Colors.BG2, fg=Colors.FG2,
        ).pack()

        # Store reference so we can update it
        if var == self.volume:
            self.bgm_vol_label = label
        else:
            self.video_vol_label = label

        # Indicators
        indicators = tk.Frame(parent, bg=Colors.BG2)
        indicators.pack(fill="x", pady=(4, 0))
        tk.Label(indicators, text="◀  Im lặng (0%)",
                 font=("Segoe UI", 8), bg=Colors.BG2, fg=Colors.FG2).pack(side="left")
        tk.Label(indicators, text="Bình thường (100%)",
                 font=("Segoe UI", 8), bg=Colors.BG2, fg=Colors.FG2).pack(side="left", padx=(0, 16))
        tk.Label(indicators, text="Tối đa (200%)",
                 font=("Segoe UI", 8), bg=Colors.BG2, fg=Colors.FG2).pack(side="right")

        # Presets
        if presets:
            presets_frame = tk.Frame(parent, bg=Colors.BG2)
            presets_frame.pack(fill="x", pady=(8, 0))
            tk.Label(presets_frame, text="Mẫu nhanh:",
                     font=("Segoe UI", 8), bg=Colors.BG2, fg=Colors.FG2).pack(side="left", padx=(0, 8))

            # Group presets in pairs of (label, value)
            items = list(presets)
            for i in range(0, len(items), 2):
                label = items[i]
                value = items[i+1]
                btn = tk.Button(
                    presets_frame, text=label,
                    font=("Segoe UI", 8),
                    bg=Colors.BG3, fg=Colors.FG,
                    relief="flat", bd=0,
                    padx=10, pady=2,
                    cursor="hand2",
                    activebackground=Colors.ACCENT, activeforeground=Colors.WHITE,
                    command=lambda v=value, vvar=var, cb=callback: (
                        vvar.set(v), cb(None)
                    ),
                )
                btn.pack(side="left", padx=(0, 6))

    # ── Event Handlers ─────────────────────────────────────────────────────

    def _on_bgm_volume_change(self, event=None):
        """Update BGM volume display label."""
        val = int(self.volume.get())
        self.bgm_vol_label.config(text=f"{val}%")

    def _on_video_volume_change(self, event=None):
        """Update video volume display label."""
        val = int(self.video_volume.get())
        self.video_vol_label.config(text=f"{val}%")

    def _select_video(self):
        """Open file dialog to select a video file."""
        path = filedialog.askopenfilename(
            title="Chọn video",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.video_path.set(path)
            self._update_file_info("video")

    def _select_audio(self):
        """Open file dialog to select an audio file."""
        path = filedialog.askopenfilename(
            title="Chọn audio",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.flac *.aac *.ogg *.m4a *.wma"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.audio_path.set(path)
            self._update_file_info("audio")

    def _update_file_info(self, file_type):
        """Update file info display (duration, size)."""
        if file_type == "video":
            path = self.video_path.get()
            if path and os.path.exists(path):
                dur = get_file_duration(path)
                size = os.path.getsize(path)
                name = os.path.basename(path)
                self.video_info_text.set(
                    f"📄 {name}  •  ⏱ {format_duration(dur)}  •  📦 {format_size(size)}"
                )
            else:
                self.video_info_text.set("Chưa chọn video")
        else:
            path = self.audio_path.get()
            if path and os.path.exists(path):
                dur = get_file_duration(path)
                size = os.path.getsize(path)
                name = os.path.basename(path)
                self.audio_info_text.set(
                    f"📄 {name}  •  ⏱ {format_duration(dur)}  •  📦 {format_size(size)}"
                )
            else:
                self.audio_info_text.set("Chưa chọn audio")

    def _validate_inputs(self):
        """Validate that video and audio files are selected and exist."""
        video = self.video_path.get()
        audio = self.audio_path.get()

        if not video or not os.path.exists(video):
            messagebox.showwarning(
                "Thiếu video",
                "Vui lòng chọn một file video trước!"
            )
            return False

        if not audio or not os.path.exists(audio):
            messagebox.showwarning(
                "Thiếu audio",
                "Vui lòng chọn một file audio trước!"
            )
            return False

        return True

    def _set_processing(self, processing, status="", progress=0):
        """Toggle UI state during processing."""
        self.is_processing = processing
        state = "disabled" if processing else "normal"

        self.btn_preview.config(state=state)
        self.btn_export.config(state=state)
        self.btn_video.config(state=state)
        self.btn_audio.config(state=state)
        self.video_entry.config(state=state)
        self.audio_entry.config(state=state)
        self.loop_checkbox.config(state=state)

        if processing:
            self.btn_cancel.config(state="normal")
            self.btn_preview.config(bg=Colors.BG3, fg=Colors.FG2)
            self.btn_export.config(bg=Colors.BG3, fg=Colors.FG2)
            self.status_icon.config(fg=Colors.WARNING)
            self.progress_value.set(progress)
        else:
            self.btn_cancel.config(state="disabled")
            self.btn_preview.config(bg=Colors.ACCENT, fg=Colors.WHITE)
            self.btn_export.config(bg=Colors.SUCCESS, fg=Colors.WHITE)
            self.status_icon.config(fg=Colors.SUCCESS)

        if status:
            self.status_text.set(status)

    def _cancel_operation(self):
        """Cancel the current ffmpeg operation."""
        self.should_cancel = True
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.ffmpeg_process.terminate()
            self.status_text.set("⏹ Đã huỷ")
            self.status_icon.config(fg=Colors.ERROR)
        self._set_processing(False, "Đã huỷ thao tác")

    # ── FFmpeg Operations ──────────────────────────────────────────────────

    def _build_ffmpeg_mix_cmd(self, video, audio, bgm_vol_factor, video_vol_factor,
                              output, has_video_audio=True, loop_audio=False, preview=False):
        """Build ffmpeg command to mix background audio with video.

        Args:
            bgm_vol_factor: Âm lượng nhạc nền (0.0 - 2.0)
            video_vol_factor: Âm lượng video gốc (0.0 - 2.0)
            loop_audio: Nếu True, loop nhạc nền nếu ngắn hơn video
            preview: Nếu True, chỉ lấy 15s đầu
        """
        cmd = [FFMPEG_CMD, "-y", "-i", video]

        if loop_audio:
            cmd += ["-stream_loop", "-1", "-i", audio]
        else:
            cmd += ["-i", audio]

        if has_video_audio:
            # Mix background audio (với âm lượng tuỳ chỉnh) với video gốc (với âm lượng tuỳ chỉnh)
            filter_complex = (
                f"[0:a]volume={video_vol_factor}[vsrc];"
                f"[1:a]volume={bgm_vol_factor}[bgm];"
                f"[vsrc][bgm]amix=inputs=2:duration=first:dropout_transition=2[outa]"
            )
            cmd += ["-filter_complex", filter_complex]
            if preview:
                cmd += ["-t", "15"]
            cmd += [
                "-map", "0:v",
                "-map", "[outa]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output,
            ]
        else:
            # Video không có audio -> chỉ thêm nhạc nền
            filter_complex = f"[1:a]volume={bgm_vol_factor}[outa]"
            cmd += ["-filter_complex", filter_complex]
            if preview:
                cmd += ["-t", "15"]
            cmd += [
                "-map", "0:v:0",
                "-map", "[outa]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output,
            ]

        return cmd

    def _run_ffmpeg(self, cmd, total_duration):
        """Run an ffmpeg command and monitor progress."""
        self.ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # Monitor progress from stderr
        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
        last_progress = 0

        while True:
            if self.should_cancel:
                self.ffmpeg_process.terminate()
                return False

            line = self.ffmpeg_process.stderr.readline()
            if not line and self.ffmpeg_process.poll() is not None:
                break

            if total_duration > 0:
                match = time_pattern.search(line)
                if match:
                    h, m, s, ms = map(int, match.groups())
                    current_time = h * 3600 + m * 60 + s + ms / 100
                    progress = min(99, int((current_time / total_duration) * 100))
                    if progress > last_progress:
                        last_progress = progress
                        self.root.after(0, lambda p=progress: self.progress_value.set(p))

        self.ffmpeg_process.wait()
        success = self.ffmpeg_process.returncode == 0
        self.ffmpeg_process = None
        return success

    # ── Preview ─────────────────────────────────────────────────────────────

    def _preview(self):
        """Generate a 15-second preview and open with default player."""
        if self.is_processing:
            return

        if not self._validate_inputs():
            return

        video = self.video_path.get()
        audio = self.audio_path.get()
        bgm_vol = self.volume.get() / 100.0
        video_vol = self.video_volume.get() / 100.0
        loop_on = self.loop_audio.get()
        vid_dur = get_file_duration(video)

        if vid_dur <= 0:
            messagebox.showerror("Lỗi", "Không thể đọc thông tin video!")
            return

        has_audio = video_has_audio(video)

        # Xoá file preview cũ nếu có
        old_preview = TEMP_DIR / "preview_temp.mp4"
        if old_preview.exists():
            try:
                old_preview.unlink()
            except Exception:
                pass

        self.should_cancel = False
        self._set_processing(True, "🔄 Đang tạo bản nghe thử...", 0)

        def worker():
            cancelled = False
            try:
                preview_path = TEMP_DIR / "preview_temp.mp4"

                cmd = self._build_ffmpeg_mix_cmd(
                    video, audio, bgm_vol, video_vol, str(preview_path),
                    has_video_audio=has_audio, loop_audio=loop_on, preview=True,
                )

                preview_dur = min(15, vid_dur)
                success = self._run_ffmpeg(cmd, preview_dur)

                if self.should_cancel:
                    cancelled = True
                    self.root.after(0, lambda: (
                        self._set_processing(False, "⏹ Đã huỷ nghe thử", 0)))
                    return

                if success and preview_path.exists():
                    self.root.after(0, lambda: self.progress_value.set(100))
                    self.root.after(0, lambda: self.status_text.set(
                        "🔊 Đang mở bản nghe thử..."))
                    os.startfile(str(preview_path))
                    self.root.after(0, lambda: self.status_text.set(
                        "✅ Bản nghe thử đã được mở"))
                else:
                    self.root.after(0, lambda: self.status_text.set(
                        "❌ Lỗi: Không thể tạo bản nghe thử"))

            except Exception as e:
                self.root.after(0, lambda: self.status_text.set(f"❌ Lỗi: {str(e)}"))
            finally:
                if not cancelled:
                    self.root.after(0, lambda: self._set_processing(False, "Sẵn sàng"))

        threading.Thread(target=worker, daemon=True).start()

    # ── Export ──────────────────────────────────────────────────────────────

    def _export(self):
        """Export the final video with background audio mixed in."""
        if self.is_processing:
            return

        if not self._validate_inputs():
            return

        video = self.video_path.get()
        audio = self.audio_path.get()
        bgm_vol = self.volume.get() / 100.0
        video_vol = self.video_volume.get() / 100.0
        loop_on = self.loop_audio.get()
        vid_dur = get_file_duration(video)

        if vid_dur <= 0:
            messagebox.showerror("Lỗi", "Không thể đọc thông tin video!")
            return

        has_video_audio = video_has_audio(video)

        # Ask for output path
        video_name = Path(video).stem
        default_name = f"{video_name}_with_bgm.mp4"

        output_path = filedialog.asksaveasfilename(
            title="Lưu video thành phẩm",
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("MP4 Video", "*.mp4"), ("All files", "*.*")],
        )

        if not output_path:
            return

        self.should_cancel = False
        self._set_processing(True, "🔄 Đang xuất video...", 0)

        def worker():
            cancelled = False
            try:
                cmd = self._build_ffmpeg_mix_cmd(
                    video, audio, bgm_vol, video_vol, output_path,
                    has_video_audio=has_video_audio,
                    loop_audio=loop_on,
                    preview=False,
                )

                success = self._run_ffmpeg(cmd, vid_dur)

                if self.should_cancel:
                    cancelled = True
                    # Clean up partial output
                    try:
                        if os.path.exists(output_path):
                            os.remove(output_path)
                    except Exception:
                        pass
                    self.root.after(0, lambda: self._set_processing(
                        False, "⏹ Đã huỷ xuất video", 0))
                    return

                if success and os.path.exists(output_path):
                    out_size = format_size(os.path.getsize(output_path))
                    self.root.after(0, lambda s=out_size: self.progress_value.set(100))
                    self.root.after(0, lambda s=out_size: self.status_text.set(
                        f"✅ Xuất thành công! ({s})"))
                    self.root.after(0, self._save_config)

                    # Ask to open
                    def ask_open(size=out_size):
                        if messagebox.askyesno(
                            "Hoàn tất",
                            f"Video đã được lưu tại:\n{output_path}\n\n"
                            f"Kích thước: {size}\n\n"
                            f"Mở video để xem kết quả?"
                        ):
                            os.startfile(output_path)

                    self.root.after(200, ask_open)
                else:
                    self.root.after(0, lambda: self.status_text.set(
                        "❌ Lỗi: Không thể xuất video"))

            except Exception as e:
                self.root.after(0, lambda: self.status_text.set(f"❌ Lỗi: {str(e)}"))
            finally:
                if not cancelled:
                    self.root.after(0, lambda: self._set_processing(False, "Sẵn sàng"))

        threading.Thread(target=worker, daemon=True).start()

    # ── Config Persistence ─────────────────────────────────────────────────

    def _load_config(self):
        """Load saved configuration from previous session."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)

                if "volume" in config:
                    self.volume.set(config["volume"])
                    self._on_bgm_volume_change()

                if "video_volume" in config:
                    self.video_volume.set(config["video_volume"])
                    self._on_video_volume_change()

                if "loop_audio" in config:
                    self.loop_audio.set(config["loop_audio"])

                if "video_path" in config and os.path.exists(config["video_path"]):
                    self.video_path.set(config["video_path"])
                    self._update_file_info("video")
                    self.video_entry.config(state="readonly")

                if "audio_path" in config and os.path.exists(config["audio_path"]):
                    self.audio_path.set(config["audio_path"])
                    self._update_file_info("audio")
                    self.audio_entry.config(state="readonly")

                # Last output directory
                self._last_output_dir = config.get("last_output_dir", "")
            else:
                self._last_output_dir = ""
        except Exception:
            self._last_output_dir = ""

    def _save_config(self):
        """Save current configuration to file."""
        try:
            config = {
                "volume": self.volume.get(),
                "video_volume": self.video_volume.get(),
                "loop_audio": self.loop_audio.get(),
                "video_path": self.video_path.get(),
                "audio_path": self.audio_path.get(),
                "last_output_dir": str(Path(self.video_path.get()).parent)
                if self.video_path.get() else "",
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def _on_close(self):
        """Clean up on window close."""
        # Cancel any running process
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.ffmpeg_process.terminate()

        # Save config
        self._save_config()

        # Clean up temp files
        try:
            for f in TEMP_DIR.iterdir():
                if f.is_file() and f.name.startswith("preview_"):
                    f.unlink()
        except Exception:
            pass

        self.root.destroy()


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    try:
        # Try to use light title bar
        root.tk.call("tk", "scaling", 1.0)
    except Exception:
        pass
    app = AudioBackgroundApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
