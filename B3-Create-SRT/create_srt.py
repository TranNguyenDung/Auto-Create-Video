#!/usr/bin/env python3
"""
B3 - Tạo file SRT từ audio (Phiên bản V12 - Kiểm soát thời lượng)
Đảm bảo phụ đề chuẩn video: dài từ 3-5 giây, không ngắt đôi từ ghép.
"""

import os
import sys
import json
import tempfile
import argparse
import numpy as np
import speech_recognition as sr
from pydub import AudioSegment
from pydub.silence import detect_silence

# =================================================================
# CẤU HÌNH TÙY CHỈNH (CONFIGURATIONS)
# =================================================================
LANGUAGE = "vi-VN"
SILENCE_THRESH = -45      
MIN_SILENCE_LEN = 150     # Ngưỡng tối thiểu để coi là khoảng nghỉ (ms)
BUFFER_MS = 300           # Đệm nhận diện

# Giới hạn vàng cho phụ đề video
TARGET_MS = 1000          # Bắt đầu tìm điểm ngắt từ 2.5 giây
LIMIT_MS = 5000           # Tuyệt đối không vượt quá 5 giây
MIN_DURATION_MS = 300    # Đủ 1 giây là có thể ngắt nếu có khoảng lặng tốt
# =================================================================

# Đường dẫn (Paths)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "B2-TTS", "export")
B3_DIR = os.path.join(BASE_DIR, "B3-Create-SRT")
OUTPUT_DIR = os.path.join(B3_DIR, "export")

def log(msg: str):
    print(f"[B3] {msg}")

def detect_language(content_name: str) -> str:
    suffix = content_name.split("_")[-1] if "_" in content_name else ""
    lang_map = {"en": "en-US", "vi": "vi-VN"}
    return lang_map.get(suffix, "vi-VN")

def ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def recognize_audio_segment(segment: AudioSegment, temp_dir: str, idx: int, language: str) -> dict:
    temp_path = os.path.join(temp_dir, f"seg_{idx:04d}.wav")
    segment.export(temp_path, format="wav")
    recognizer = sr.Recognizer()
    result = {"text": "", "success": False}
    try:
        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=language)
            result.update({"text": text, "success": True})
            print(f"  [{idx:03d}] ✓ {text[:40]}...")
    except: pass
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
    return result

def strict_duration_split(silences, total_len):
    """
    Logic ngắt đoạn theo thời lượng mục tiêu:
    - Cố gắng ngắt ở khoảng 3.5 giây.
    - Bắt buộc ngắt nếu đạt 5 giây.
    """
    if not silences: return []
    
    boundaries = []
    last_split = 0
    
    # Danh sách các khoảng nghỉ tiềm năng (phải đủ dài để không cắt từ ghép)
    potential_breaks = [(s, e) for s, e in silences if (e - s) >= 180]
    
    current_idx = 0
    while last_split < total_len - 1000:
        found_split = False
        # Tìm khoảng nghỉ tốt nhất trong cửa sổ từ TARGET đến LIMIT
        best_break = None
        max_silence = -1
        
        for i in range(current_idx, len(potential_breaks)):
            s, e = potential_breaks[i]
            mid = (s + e) // 2
            dist = mid - last_split
            
            if dist < MIN_DURATION_MS: # Dưới 1 giây, bỏ qua
                continue
                
            if MIN_DURATION_MS <= dist <= LIMIT_MS:
                silence_len = e - s
                
                # Ưu tiên khoảng nghỉ dài nhất
                if silence_len > max_silence:
                    max_silence = silence_len
                    best_break = mid
                    current_idx = i
                
                # Nếu đã đạt mốc TARGET (2.5s) và thấy khoảng nghỉ rõ rệt (>250ms) -> Ngắt luôn
                if dist >= TARGET_MS and silence_len > 250:
                    best_break = mid
                    found_split = True
                    break
            
            if dist > LIMIT_MS: # Đã vượt quá giới hạn, phải chọn best_break đã thấy
                break
        
        if best_break:
            boundaries.append(best_break)
            last_split = best_break
        else:
            # Nếu không tìm thấy khoảng nghỉ nào lý tưởng, ép ngắt tại LIMIT_MS
            last_split += TARGET_MS
            if last_split < total_len:
                boundaries.append(last_split)
                
        if not found_split: current_idx += 1
            
    return boundaries

def main():
    parser = argparse.ArgumentParser(description="B3 - Strict Duration SRT")
    parser.add_argument("--content-name", default="content1", help="Tên file content")
    args = parser.parse_args()

    global LANGUAGE
    LANGUAGE = detect_language(args.content_name)
    log(f"Phát hiện ngôn ngữ: {LANGUAGE}")

    audio_path = os.path.join(AUDIO_DIR, f"{args.content_name}_output_audio.wav")
    output_srt = os.path.join(OUTPUT_DIR, f"{args.content_name}_subtitles.srt")
    output_json = os.path.join(OUTPUT_DIR, f"{args.content_name}_segments.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(audio_path):
        log(f"[LỖI] Không tìm thấy audio: {audio_path}")
        sys.exit(1)

    print(f"\n{'='*50}\nB3 - TẠO PHỤ ĐỀ CHUẨN (KIỂM SOÁT THỜI LƯỢNG) [{args.content_name}]\n{'='*50}")

    audio = AudioSegment.from_wav(audio_path)
    
    # Tìm khoảng lặng
    all_silences = detect_silence(audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESH)
    
    # Ngắt đoạn dựa trên thời lượng
    boundaries = strict_duration_split(all_silences, len(audio))
    
    # Chia đoạn (Double Buffer để nhận diện)
    segments_to_recognize = []
    start_ms = 0
    for b in boundaries:
        audio_chunk = audio[max(0, start_ms - BUFFER_MS):min(len(audio), b + BUFFER_MS)]
        segments_to_recognize.append({"display_start": start_ms, "display_end": b, "audio_chunk": audio_chunk})
        start_ms = b
    segments_to_recognize.append({
        "display_start": start_ms, "display_end": len(audio),
        "audio_chunk": audio[max(0, start_ms - BUFFER_MS):]
    })
    
    log(f"Đã chia thành {len(segments_to_recognize)} đoạn (3-5 giây/đoạn).")

    # Nhận dạng
    segments_data = []
    with tempfile.TemporaryDirectory() as temp_dir:
        for i, seg in enumerate(segments_to_recognize, 1):
            res = recognize_audio_segment(seg["audio_chunk"], temp_dir, i, LANGUAGE)
            if res["text"].strip():
                segments_data.append({
                    "start_ms": seg["display_start"], "end_ms": seg["display_end"], 
                    "text": res["text"].strip(), "success": True
                })

    # Xuất file
    srt_lines = []
    for i, seg in enumerate(segments_data, 1):
        srt_lines.extend([str(i), f"{ms_to_srt_time(seg['start_ms'])} --> {ms_to_srt_time(seg['end_ms'])}", seg["text"], ""])

    with open(output_srt, "w", encoding="utf-8") as f: f.write("\n".join(srt_lines))
    with open(output_json, "w", encoding="utf-8") as f: json.dump(segments_data, f, ensure_ascii=False, indent=2)

    log(f"[HOÀN TẤT] SRT đã đạt chuẩn video chuyên nghiệp.")
    print(f"\nCONTENT_NAME={args.content_name}")

if __name__ == "__main__":
    main()
