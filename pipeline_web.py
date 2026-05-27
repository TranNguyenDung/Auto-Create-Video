#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline Web - Giao diện web quản lý quy trình tạo video tự động
Thay thế cho pipeline_manager.py (Tkinter) bằng Flask + HTML/CSS/JS
"""

import os
import sys
import re
import json
import time
import threading
import subprocess
import queue
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response, stream_with_context

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
CONTENT_DIR = BASE_DIR / "B1-Content"
HISTORY_FILE = BASE_DIR / "pipeline_history.json"
AUDIO_BG_APP = BASE_DIR / "AudioBackground" / "app.py"

STEPS = ["B2", "B3", "B4", "B5"]
STEP_NAMES = {
    "B1": "📝 Nội dung",
    "B2": "🔊 TTS (Text→Audio)",
    "B3": "📜 SRT (Audio→Phụ đề)",
    "B4": "✅ Xác thực SRT",
    "B5": "🎬 Tạo Video",
}
STEP_ICONS = {"B1": "📝", "B2": "🔊", "B3": "📜", "B4": "✅", "B5": "🎬"}
SCRIPTS = {
    "B2": BASE_DIR / "B2-TTS" / "tts.py",
    "B3": BASE_DIR / "B3-Create-SRT" / "create_srt.py",
    "B4": BASE_DIR / "B4-Verify-SRT" / "verify_srt.py",
    "B5": BASE_DIR / "B5-Create-Video" / "create_video_ass.py",
}
STEP_OUTPUTS = {
    "B1": lambda n: CONTENT_DIR / f"{n}.txt",
    "B2": lambda n: BASE_DIR / "B2-TTS" / "export" / f"{n}_output_audio.wav",
    "B3": lambda n: BASE_DIR / "B3-Create-SRT" / "export" / f"{n}_subtitles.srt",
    "B4": lambda n: BASE_DIR / "B4-Verify-SRT" / "export" / f"{n}_subtitles_verified.srt",
    "B5_16_9": lambda n: BASE_DIR / "B5-Create-Video" / "export" / n / f"{n}_ass_16_9.mp4",
    "B5_9_16": lambda n: BASE_DIR / "B5-Create-Video" / "export" / n / f"{n}_ass_9_16.mp4",
    "B5": lambda n: BASE_DIR / "B5-Create-Video" / "export" / n / f"{n}_ass_16_9.mp4",
}

app = Flask(__name__)

# ─── Pipeline State ───────────────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "content_name": "",
    "current_step": "",
    "progress": 0,
    "status": "idle",
    "process": None,
    "should_cancel": False,
    "start_time": 0,
}
log_queue = queue.Queue()
log_history = []

# ─── Schedule State ───────────────────────────────────────────
schedule_state = {
    "active": False,
    "contents": [],
    "current_index": -1,
    "current_content": "",
    "shutdown": False,
    "cancel": False,
    "status": "idle",
    "progress": 0,
}


# ─── Helper Functions ─────────────────────────────────────────────────────────
def get_file_size_str(path):
    try:
        size = os.path.getsize(path)
        if size < 1024: return f"{size} B"
        elif size < 1024 * 1024: return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024: return f"{size / (1024 * 1024):.1f} MB"
        else: return f"{size / (1024 * 1024 * 1024):.1f} GB"
    except: return "?"


def get_file_mtime(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except: return ""


def count_lines(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except: return 0


def get_video_duration(path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except: pass
    return 0


def format_duration(seconds):
    if seconds <= 0: return "--:--"
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def natural_sort_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

def list_content_files():
    if not CONTENT_DIR.exists(): return []
    return sorted([f.stem for f in CONTENT_DIR.iterdir()
                   if f.suffix == ".txt" and f.stem.startswith("content")],
                  key=natural_sort_key)


def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"runs": [], "contents": {}}


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_log_sync("error", f"Không thể lưu history: {e}")


def add_run_to_history(content_name, steps_run, status, duration_sec, output_files=None):
    history = load_history()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "content_name": content_name,
        "steps_run": steps_run,
        "status": status,
        "duration_sec": round(duration_sec, 1),
        "output_files": output_files or [],
    }
    history["runs"].append(entry)
    if len(history["runs"]) > 100:
        history["runs"] = history["runs"][-100:]

    if content_name not in history["contents"]:
        history["contents"][content_name] = {
            "last_run": None, "run_count": 0,
            "success_count": 0, "fail_count": 0,
            "metadata": {"youtube": False, "youtube_shorts": False, "tiktok": False, "facebook": False, "note": ""},
        }
    info = history["contents"][content_name]
    if "metadata" not in info:
        info["metadata"] = {"youtube": False, "youtube_shorts": False, "tiktok": False, "facebook": False, "note": ""}
    info["last_run"] = datetime.now().isoformat()
    info["run_count"] += 1
    if status == "success": info["success_count"] += 1
    else: info["fail_count"] += 1
    save_history(history)
    return history


def add_log_sync(tag, message):
    """Add log entry from any thread. Thread-safe via queue."""
    entry = {"tag": tag, "message": message, "timestamp": datetime.now().strftime("%H:%M:%S")}
    log_history.append(entry)
    if len(log_history) > 1000:
        log_history[:200] = []
    log_queue.put(entry)


def get_content_status(content_name):
    steps_status = {}
    all_done = True
    partial = False
    b1_exists = STEP_OUTPUTS["B1"](content_name).exists()
    steps_status["B1"] = b1_exists
    for step in STEPS:
        exists = STEP_OUTPUTS[step](content_name).exists()
        steps_status[step] = exists
        if not exists: all_done = False
        if exists: partial = True
    return {"steps": steps_status, "all_done": all_done, "partial": partial}


def get_content_details(content_name):
    path = CONTENT_DIR / f"{content_name}.txt"
    status = get_content_status(content_name)
    history = load_history()
    ch = history.get("contents", {}).get(content_name, {})
    meta = ch.get("metadata", {"youtube": False, "youtube_shorts": False, "tiktok": False, "facebook": False, "note": ""})

    details = {
        "name": content_name,
        "exists": path.exists(),
        "size": get_file_size_str(path) if path.exists() else "",
        "lines": count_lines(path) if path.exists() else 0,
        "mtime": get_file_mtime(path) if path.exists() else "",
        "steps": status["steps"],
        "all_done": status["all_done"],
        "partial": status["partial"],
        "metadata": meta,
        "last_run": ch.get("last_run", ""),
        "run_count": ch.get("run_count", 0),
        "success_count": ch.get("success_count", 0),
        "fail_count": ch.get("fail_count", 0),
    }

    # Step details with output info
    for s in ["B1"] + STEPS:
        if status["steps"].get(s):
            out = STEP_OUTPUTS[s](content_name) if s != "B1" else path
            if out and out.exists():
                info = {"exists": True, "size": get_file_size_str(out)}
                if s in ("B2", "B5"):
                    dur = get_video_duration(str(out))
                    if dur > 0: info["duration"] = format_duration(dur)
                details[f"step_{s}_info"] = info

    return details


# ─── Flask Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/contents")
def api_contents():
    files = list_content_files()
    contents = []
    for fname in files:
        status = get_content_status(fname)
        meta = load_history().get("contents", {}).get(fname, {}).get("metadata", {})
        contents.append({
            "name": fname,
            "status": "done" if status["all_done"] else ("partial" if status["partial"] else "pending"),
            "steps": status["steps"],
            "youtube": meta.get("youtube", False),
            "youtube_shorts": meta.get("youtube_shorts", False),
            "tiktok": meta.get("tiktok", False),
            "facebook": meta.get("facebook", False),
            "note": meta.get("note", ""),
        })
    return jsonify(contents)


@app.route("/api/contents/<name>")
def api_content_detail(name):
    return jsonify(get_content_details(name))


@app.route("/api/contents/<name>/metadata", methods=["GET", "POST"])
def api_content_metadata(name):
    history = load_history()
    if request.method == "POST":
        data = request.get_json()
        if name not in history["contents"]:
            history["contents"][name] = {
                "last_run": None, "run_count": 0,
                "success_count": 0, "fail_count": 0,
                "metadata": {"youtube": False, "tiktok": False, "note": ""},
            }
        history["contents"][name]["metadata"] = {
            "youtube": data.get("youtube", False),
            "youtube_shorts": data.get("youtube_shorts", False),
            "tiktok": data.get("tiktok", False),
            "facebook": data.get("facebook", False),
            "note": data.get("note", ""),
        }
        save_history(history)
        return jsonify({"status": "ok"})

    meta = history.get("contents", {}).get(name, {}).get("metadata", {})
    return jsonify({"youtube": meta.get("youtube", False),
                    "youtube_shorts": meta.get("youtube_shorts", False),
                    "tiktok": meta.get("tiktok", False),
                    "facebook": meta.get("facebook", False),
                    "note": meta.get("note", "")})


@app.route("/api/pipeline/start", methods=["POST"])
def api_pipeline_start():
    data = request.get_json()
    content_name = data.get("content_name", "")
    start_step = data.get("start_step", "B2")

    if not content_name:
        return jsonify({"error": "Missing content_name"}), 400

    # Race-condition guard
    if pipeline_state.get("_starting", False):
        return jsonify({"error": "Đang khởi tạo, vui lòng chờ..."}), 429
    pipeline_state["_starting"] = True
    try:
        if pipeline_state["running"]:
            return jsonify({"error": "Pipeline already running"}), 400

        content_path = CONTENT_DIR / f"{content_name}.txt"
        if not content_path.exists():
            return jsonify({"error": f"Content not found: {content_path}"}), 404

        if start_step not in STEPS and start_step != "ALL":
            return jsonify({"error": f"Invalid start_step: {start_step}. Must be one of {STEPS}"}), 400

        steps_to_run = STEPS[STEPS.index(start_step):] if start_step in STEPS else STEPS

        # Reset pipeline state
        pipeline_state["running"] = True
        pipeline_state["content_name"] = content_name
        pipeline_state["current_step"] = ""
        pipeline_state["progress"] = 0
        pipeline_state["status"] = "running"
        pipeline_state["should_cancel"] = False
        pipeline_state["start_time"] = time.time()

        # Clear log
        log_history.clear()
        while not log_queue.empty():
            log_queue.get()

        add_log_sync("header", "=" * 50)
        add_log_sync("header", f"  BẮT ĐẦU PIPELINE: {content_name}")
        add_log_sync("header", f"  Các bước: {' → '.join([STEP_NAMES[s] for s in steps_to_run])}")
        add_log_sync("header", "=" * 50)

        # Start pipeline in background thread
        threading.Thread(target=_run_pipeline_thread,
                         args=(content_name, steps_to_run),
                         daemon=True).start()

        return jsonify({"status": "started", "content_name": content_name, "steps": steps_to_run})
    finally:
        pipeline_state["_starting"] = False


def _run_pipeline_thread(content_name, steps_to_run):
    start_time = time.time()
    overall_status = "success"
    completed_steps = []
    output_files = []
    total = len(steps_to_run)

    for idx, step in enumerate(steps_to_run):
        if pipeline_state["should_cancel"]:
            overall_status = "cancelled"
            break

        pipeline_state["current_step"] = step
        pipeline_state["progress"] = (idx / total) * 100

        add_log_sync("info", "")
        add_log_sync("info", f"▶ Bước {step}: {STEP_NAMES[step]}...")

        script = SCRIPTS[step]
        if not script.exists():
            add_log_sync("error", f"❌ Không tìm thấy script: {script}")
            overall_status = "fail"
            break

        cmd = [sys.executable, "-X", "utf8", str(script), "--content-name", content_name]
        add_log_sync("info", f"  $ {' '.join(cmd)}")

        step_start = time.time()
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", bufsize=1, cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            pipeline_state["process"] = proc

            for line in iter(proc.stdout.readline, ""):
                if pipeline_state["should_cancel"]:
                    proc.terminate()
                    break
                if line.strip():
                    add_log_sync("info", f"  {line.rstrip()}")

            proc.wait()
            step_elapsed = time.time() - step_start

            if proc.returncode == 0:
                completed_steps.append(step)
                add_log_sync("success", f"  ✓ {STEP_NAMES[step]} hoàn tất ({step_elapsed:.1f}s)")
                out_path = STEP_OUTPUTS[step](content_name)
                if out_path and out_path.exists():
                    output_files.append(str(out_path))
            else:
                overall_status = "fail"
                add_log_sync("error", f"  ❌ {STEP_NAMES[step]} thất bại (mã lỗi: {proc.returncode})")
                break

            pipeline_state["process"] = None
        except Exception as e:
            overall_status = "fail"
            add_log_sync("error", f"  ❌ Lỗi: {str(e)}")
            pipeline_state["process"] = None
            break

    total_elapsed = time.time() - start_time

    # Check for video outputs
    for key in ["B5_16_9", "B5_9_16"]:
        p = STEP_OUTPUTS[key](content_name)
        if p.exists():
            output_files.append(str(p))

    if overall_status == "success":
        add_log_sync("success", "")
        add_log_sync("success", "=" * 50)
        add_log_sync("success", f"  ✅ PIPELINE HOÀN TẤT! ({format_duration(total_elapsed)})")
        add_log_sync("success", "=" * 50)
        pipeline_state["progress"] = 100
    elif overall_status == "cancelled":
        add_log_sync("warn", "⏹ Pipeline đã bị huỷ.")
        pipeline_state["progress"] = 0
        add_log_sync("warn", "=" * 50)
    else:
        add_log_sync("error", f"❌ Pipeline thất bại sau {format_duration(total_elapsed)}")
        pipeline_state["progress"] = 0

    add_run_to_history(content_name, completed_steps, overall_status, total_elapsed, output_files)

    pipeline_state["running"] = False
    pipeline_state["status"] = overall_status

    # Push a final marker for SSE
    add_log_sync("__done__", overall_status)


@app.route("/api/pipeline/status")
def api_pipeline_status():
    return jsonify({
        "running": pipeline_state["running"],
        "content_name": pipeline_state["content_name"],
        "current_step": pipeline_state["current_step"],
        "step_name": STEP_NAMES.get(pipeline_state["current_step"], ""),
        "progress": pipeline_state["progress"],
        "status": pipeline_state["status"],
        "elapsed": time.time() - pipeline_state["start_time"] if pipeline_state["running"] else 0,
    })


@app.route("/api/pipeline/stream")
def api_pipeline_stream():
    def generate():
        last_index = len(log_history)
        # Send existing logs first
        for entry in log_history:
            yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
        last_index = len(log_history)

        # Wait for new logs
        while pipeline_state["running"] or not log_queue.empty():
            try:
                entry = log_queue.get(timeout=1)
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                if entry.get("tag") == "__done__":
                    break
            except queue.Empty:
                yield ": keepalive\n\n"
        # Send remaining
        while not log_queue.empty():
            try:
                entry = log_queue.get_nowait()
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            except queue.Empty:
                break

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    })


@app.route("/api/pipeline/cancel", methods=["POST"])
def api_pipeline_cancel():
    if not pipeline_state["running"]:
        return jsonify({"error": "No pipeline running"}), 400
    pipeline_state["should_cancel"] = True
    if pipeline_state["process"] and pipeline_state["process"].poll() is None:
        pipeline_state["process"].terminate()
    add_log_sync("warn", "⏹ Đã yêu cầu huỷ pipeline...")
    return jsonify({"status": "cancelling"})


# ─── Schedule Routes ──────────────────────────────────────────

@app.route("/api/schedule/start", methods=["POST"])
def api_schedule_start():
    data = request.get_json()
    from_name = data.get("from", "")
    to_name = data.get("to", "")
    shutdown = data.get("shutdown", False)
    time_from = data.get("time_from", "")   # "13:00"
    time_to = data.get("time_to", "")       # "15:00"

    # Race-condition guard: atomic check-and-set
    if pipeline_state.get("_starting", False):
        return jsonify({"error": "Đang khởi tạo, vui lòng chờ..."}), 429
    pipeline_state["_starting"] = True
    try:
        if pipeline_state["running"] or schedule_state["active"]:
            return jsonify({"error": "Pipeline hoặc lịch chạy đang hoạt động"}), 400

        all_contents = list_content_files()
        if from_name not in all_contents or to_name not in all_contents:
            return jsonify({"error": "Tên content không hợp lệ"}), 400

        from_idx = all_contents.index(from_name)
        to_idx = all_contents.index(to_name)
        if from_idx > to_idx:
            return jsonify({"error": "'Từ' phải trước 'Đến'"}), 400

        contents = all_contents[from_idx:to_idx + 1]

        # Validate time window
        time_window = {}
        if time_from and time_to:
            try:
                tf = datetime.strptime(time_from, "%H:%M")
                tt = datetime.strptime(time_to, "%H:%M")
            except ValueError:
                return jsonify({"error": "Giờ không đúng định dạng HH:MM"}), 400
            if tf >= tt:
                return jsonify({"error": "Giờ kết thúc phải sau giờ bắt đầu"}), 400
            time_window = {"from": time_from, "to": time_to}

        # Clear log before schedule
        log_history.clear()
        while not log_queue.empty():
            try: log_queue.get_nowait()
            except queue.Empty: break

        schedule_state["active"] = True
        schedule_state["contents"] = contents
        schedule_state["current_index"] = -1
        schedule_state["current_content"] = ""
        schedule_state["shutdown"] = shutdown
        schedule_state["cancel"] = False
        schedule_state["status"] = "running"
        schedule_state["progress"] = 0
        schedule_state["time_window"] = time_window

        pipeline_state["running"] = True
        pipeline_state["status"] = "schedule"

        threading.Thread(target=_run_schedule_thread, daemon=True).start()
        return jsonify({"status": "started", "contents": contents})
    finally:
        pipeline_state["_starting"] = False


def _parse_time(t_str):
    """Parse HH:MM to (hour, minute) tuple."""
    parts = t_str.split(":")
    return int(parts[0]), int(parts[1])


def _minutes_since_midnight():
    now = datetime.now()
    return now.hour * 60 + now.minute


def _wait_until_time(target_hour, target_minute):
    """Sleep until target time today. If target time passed, return False."""
    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        return False  # Time already passed
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return True
        if schedule_state["cancel"]:
            return False
        if remaining > 60:
            mins = int(remaining // 60)
            add_log_sync("info", f"  ⏳ Chờ đến {target_hour:02d}:{target_minute:02d} — còn {mins} phút...")
            time.sleep(min(60, remaining))
        else:
            add_log_sync("info", f"  ⏳ Còn {int(remaining)} giây...")
            time.sleep(min(5, remaining))


def _run_schedule_thread():
    contents = schedule_state["contents"]
    total = len(contents)
    completed = []
    time_window = schedule_state.get("time_window", {})
    use_time_window = bool(time_window)

    # Log header
    add_log_sync("header", "=" * 50)
    add_log_sync("header", f"  📅 BẮT ĐẦU LỊCH CHẠY: {total} contents")
    add_log_sync("header", f"  {contents[0]} → {contents[-1]}")
    if use_time_window:
        add_log_sync("header", f"  ⏰ Khung giờ: {time_window['from']} → {time_window['to']}")
    if schedule_state["shutdown"]:
        add_log_sync("header", "  🔌 Sẽ tắt máy sau khi hoàn tất")
    add_log_sync("header", "=" * 50)

    # Wait for time window
    if use_time_window:
        tf_h, tf_m = _parse_time(time_window["from"])
        current_min = _minutes_since_midnight()
        start_min = tf_h * 60 + tf_m

        if current_min < start_min:
            add_log_sync("info", f"⏳ Chờ đến {time_window['from']} để bắt đầu...")
            if not _wait_until_time(tf_h, tf_m):
                add_log_sync("warn", "⏹ Đã huỷ khi đang chờ giờ chạy.")
                _finish_schedule([], total, True)
                return
            add_log_sync("info", f"✅ Đã đến giờ, bắt đầu chạy!")
        elif current_min >= start_min:
            # Check if already past end time
            tt_h, tt_m = _parse_time(time_window["to"])
            end_min = tt_h * 60 + tt_m
            if current_min >= end_min:
                add_log_sync("warn", f"⚠ Đã qua khung giờ ({time_window['from']}→{time_window['to']}), không thể chạy.")
                _finish_schedule([], total, True)
                return
            add_log_sync("info", f"✅ Đang trong khung giờ, bắt đầu ngay!")

    for idx, content_name in enumerate(contents):
        if schedule_state["cancel"]:
            add_log_sync("warn", "⏹ Đã huỷ lịch chạy.")
            break

        # Check time window before each content
        if use_time_window:
            tt_h, tt_m = _parse_time(time_window["to"])
            current_min = _minutes_since_midnight()
            end_min = tt_h * 60 + tt_m
            if current_min >= end_min:
                add_log_sync("warn", f"⏰ Đã hết khung giờ ({time_window['to']}), dừng lịch.")
                break

        schedule_state["current_index"] = idx
        schedule_state["current_content"] = content_name
        schedule_state["progress"] = int((idx / total) * 100)

        add_log_sync("info", "")
        add_log_sync("info", f"[{idx+1}/{total}] ▶ Content: {content_name}")

        success = True
        for step in STEPS:
            if schedule_state["cancel"]:
                success = False
                break

            pipeline_state["current_step"] = step
            script = SCRIPTS[step]
            cmd = [sys.executable, "-X", "utf8", str(script), "--content-name", content_name]

            add_log_sync("info", f"  Bước {step}: {STEP_NAMES[step]}")

            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", bufsize=1, cwd=str(BASE_DIR),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                pipeline_state["process"] = proc

                for line in iter(proc.stdout.readline, ""):
                    if schedule_state["cancel"]:
                        proc.terminate()
                        break
                    if line.strip():
                        add_log_sync("info", f"  {line.rstrip()}")

                proc.wait()
                if proc.returncode != 0:
                    success = False
                    add_log_sync("error", f"  ❌ Bước {step} thất bại (mã lỗi: {proc.returncode})")
                    break
                add_log_sync("success", f"  ✓ Bước {step} hoàn tất")
            except Exception as e:
                success = False
                add_log_sync("error", f"  ❌ Lỗi: {str(e)}")
                break

        pipeline_state["process"] = None

        if success:
            completed.append(content_name)
            add_run_to_history(content_name, STEPS, "success", 0)
            add_log_sync("success", f"✅ [{idx+1}/{total}] {content_name} hoàn tất!")
        else:
            if not schedule_state["cancel"]:
                add_log_sync("error", f"❌ [{idx+1}/{total}] {content_name} thất bại, dừng lịch.")
            break

    _finish_schedule(completed, total)


def _finish_schedule(completed, total, cancelled=False):
    """Finish schedule and print summary."""
    if not cancelled:
        schedule_state["progress"] = 100 if len(completed) == total else schedule_state["progress"]

    add_log_sync("info", "")
    add_log_sync("info", "=" * 50)
    add_log_sync("info", f"  📊 KẾT QUẢ: {len(completed)}/{total} thành công")

    is_cancelled = cancelled or schedule_state.get("cancel", False)
    if is_cancelled:
        add_log_sync("info", "  ⏹ Đã huỷ/kết thúc sớm")
    add_log_sync("info", "=" * 50)

    schedule_state["active"] = False
    schedule_state["status"] = "cancelled" if is_cancelled else "completed"
    pipeline_state["running"] = False
    pipeline_state["status"] = "idle"
    pipeline_state["process"] = None

    add_log_sync("__done__", "schedule_complete")

    # Shutdown if requested
    if schedule_state["shutdown"] and not is_cancelled and len(completed) == total:
        add_log_sync("warn", "🔌 Sẽ tắt máy sau 120 giây... (vào http://127.0.0.1:5000/api/shutdown/cancel để huỷ)")
        try:
            subprocess.run(["shutdown", "/s", "/t", "120"], check=False)
        except Exception as e:
            add_log_sync("error", f"❌ Không thể tắt máy: {e}")


@app.route("/api/schedule/status")
def api_schedule_status():
    time_window = schedule_state.get("time_window", {})
    waiting = False
    wait_until = ""
    if time_window and schedule_state["active"]:
        tf_h, tf_m = _parse_time(time_window["from"])
        current_min = _minutes_since_midnight()
        if current_min < tf_h * 60 + tf_m:
            waiting = True
            wait_until = time_window["from"]

    return jsonify({
        "active": schedule_state["active"],
        "contents": schedule_state["contents"],
        "current_index": schedule_state["current_index"],
        "current_content": schedule_state["current_content"],
        "shutdown": schedule_state["shutdown"],
        "status": schedule_state["status"],
        "progress": schedule_state["progress"],
        "time_window": time_window,
        "waiting": waiting,
        "wait_until": wait_until,
    })


@app.route("/api/schedule/cancel", methods=["POST"])
def api_schedule_cancel():
    if not schedule_state["active"]:
        return jsonify({"error": "Không có lịch chạy nào đang hoạt động"}), 400
    schedule_state["cancel"] = True
    if pipeline_state["process"] and pipeline_state["process"].poll() is None:
        pipeline_state["process"].terminate()
    add_log_sync("warn", "⏹ Đã yêu cầu huỷ lịch chạy...")
    return jsonify({"status": "cancelling"})


@app.route("/api/shutdown/cancel", methods=["POST"])
def api_shutdown_cancel():
    try:
        subprocess.run(["shutdown", "/a"], check=False)
        add_log_sync("info", "✅ Đã huỷ tắt máy.")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── History Routes ───────────────────────────────────────────

@app.route("/api/history")
def api_history():
    history = load_history()
    runs = []
    for entry in reversed(history.get("runs", [])):
        try:
            dt = datetime.fromisoformat(entry.get("timestamp", ""))
            ts = dt.strftime("%d/%m/%Y %H:%M:%S")
        except:
            ts = entry.get("timestamp", "")
        runs.append({
            "timestamp": ts,
            "content_name": entry.get("content_name", "?"),
            "steps_run": ", ".join(entry.get("steps_run", [])),
            "status": entry.get("status", "?"),
            "duration": format_duration(entry.get("duration_sec", 0)),
            "output_count": len(entry.get("output_files", [])),
        })
    return jsonify(runs)


@app.route("/api/history", methods=["DELETE"])
def api_clear_history():
    save_history({"runs": [], "contents": {}})
    add_log_sync("info", "🗑 Đã xoá lịch sử chạy.")
    return jsonify({"status": "ok"})


@app.route("/api/audio-bg", methods=["POST"])
def api_audio_bg():
    if not AUDIO_BG_APP.exists():
        return jsonify({"error": "AudioBackground not found"}), 404
    try:
        subprocess.Popen([sys.executable, str(AUDIO_BG_APP)],
                         cwd=str(AUDIO_BG_APP.parent),
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        add_log_sync("info", f"🎵 Đã mở AudioBackground")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/content/<name>/edit", methods=["POST"])
def api_edit_content(name):
    path = CONTENT_DIR / f"{name}.txt"
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    try:
        os.startfile(str(path))
    except Exception:
        try:
            subprocess.run(["notepad", str(path)], check=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"})


@app.route("/api/content/<name>/open-output", methods=["POST"])
def api_open_output(name):
    d = BASE_DIR / "B5-Create-Video" / "export" / name
    if d.exists():
        try:
            os.startfile(str(d))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"})


@app.route("/api/content/<name>/open-folder", methods=["POST"])
def api_open_folder(name):
    if CONTENT_DIR.exists():
        try:
            os.startfile(str(CONTENT_DIR))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"})


@app.route("/api/contents/<name>/run-history")
def api_content_run_history(name):
    history = load_history()
    runs = [r for r in history.get("runs", []) if r.get("content_name") == name]
    return jsonify(runs)


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🌐 Pipeline Web Server")
    print(f"   Mở trình duyệt tại: http://127.0.0.1:5000")
    print(f"   Nhấn Ctrl+C để dừng.")
    app.run(debug=True, threaded=True, host="127.0.0.1", port=5000)
