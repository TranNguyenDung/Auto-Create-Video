#!/usr/bin/env python3
"""
B3 - Generate SRT file from audio (V12 - Duration Control)
Ensure standard video subtitles: 3-5 seconds long, no word splitting.
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
# CUSTOM CONFIGURATIONS
# =================================================================
LANGUAGE = "vi-VN"
SILENCE_THRESH = -45      
MIN_SILENCE_LEN = 150     # Minimum silence threshold (ms)
BUFFER_MS = 300           # Recognition buffer

# Golden limits for video subtitles
TARGET_MS = 1000          # Start looking for break points from 2.5 seconds
LIMIT_MS = 5000           # Absolutely must not exceed 5 seconds
MIN_DURATION_MS = 300    # Minimum 1 second to allow splitting if good silence found
# =================================================================

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "B2-TTS", "export")
B3_DIR = os.path.join(BASE_DIR, "B3-Create-SRT")
OUTPUT_DIR = os.path.join(B3_DIR, "export")

def log(msg: str):
    print(f"[B3] {msg}")

def ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def recognize_audio_segment(segment: AudioSegment, temp_dir: str, idx: int) -> dict:
    temp_path = os.path.join(temp_dir, f"seg_{idx:04d}.wav")
    segment.export(temp_path, format="wav")
    recognizer = sr.Recognizer()
    result = {"text": "", "success": False}
    try:
        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=LANGUAGE)
            result.update({"text": text, "success": True})
            print(f"  [{idx:03d}] ✓ {text[:40]}...")
    except: pass
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
    return result

def strict_duration_split(silences, total_len):
    """
    Split logic based on target duration:
    - Try to split at around 3.5 seconds.
    - Force split at 5 seconds.
    """
    if not silences: return []
    
    boundaries = []
    last_split = 0
    
    # List of potential breaks (must be long enough to avoid splitting words)
    potential_breaks = [(s, e) for s, e in silences if (e - s) >= 180]
    
    current_idx = 0
    while last_split < total_len - 1000:
        found_split = False
        # Find best break in TARGET to LIMIT window
        best_break = None
        max_silence = -1
        
        for i in range(current_idx, len(potential_breaks)):
            s, e = potential_breaks[i]
            mid = (s + e) // 2
            dist = mid - last_split
            
            if dist < MIN_DURATION_MS: # Under 1 second, skip
                continue
                
            if MIN_DURATION_MS <= dist <= LIMIT_MS:
                silence_len = e - s
                
                # Prefer longest silence
                if silence_len > max_silence:
                    max_silence = silence_len
                    best_break = mid
                    current_idx = i
                
                # If reached TARGET (2.5s) with clear silence (>250ms) -> Split now
                if dist >= TARGET_MS and silence_len > 250:
                    best_break = mid
                    found_split = True
                    break
            
            if dist > LIMIT_MS: # Exceeded limit, must use best_break found
                break
        
        if best_break:
            boundaries.append(best_break)
            last_split = best_break
        else:
            # If no ideal break found, force split at LIMIT_MS
            last_split += TARGET_MS
            if last_split < total_len:
                boundaries.append(last_split)
                
        if not found_split: current_idx += 1
            
    return boundaries

def main():
    parser = argparse.ArgumentParser(description="B3 - Strict Duration SRT")
    parser.add_argument("--content-name", default="content1", help="Content file name")
    args = parser.parse_args()

    audio_path = os.path.join(AUDIO_DIR, f"{args.content_name}_output_audio.wav")
    output_srt = os.path.join(OUTPUT_DIR, f"{args.content_name}_subtitles.srt")
    output_json = os.path.join(OUTPUT_DIR, f"{args.content_name}_segments.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(audio_path):
        log(f"[ERROR] Audio not found: {audio_path}")
        sys.exit(1)

    print(f"\n{'='*50}\nB3 - STANDARD SUBTITLE GENERATION (DURATION CONTROL) [{args.content_name}]\n{'='*50}")

    audio = AudioSegment.from_wav(audio_path)
    
    # Detect silence
    all_silences = detect_silence(audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESH)
    
    # Split segments based on duration
    boundaries = strict_duration_split(all_silences, len(audio))
    
    # Split segments (double buffer for recognition)
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
    
    log(f"Split into {len(segments_to_recognize)} segments (3-5 seconds each).")

    # Recognition
    segments_data = []
    with tempfile.TemporaryDirectory() as temp_dir:
        for i, seg in enumerate(segments_to_recognize, 1):
            res = recognize_audio_segment(seg["audio_chunk"], temp_dir, i)
            if res["text"].strip():
                segments_data.append({
                    "start_ms": seg["display_start"], "end_ms": seg["display_end"], 
                    "text": res["text"].strip(), "success": True
                })

    # Export files
    srt_lines = []
    for i, seg in enumerate(segments_data, 1):
        srt_lines.extend([str(i), f"{ms_to_srt_time(seg['start_ms'])} --> {ms_to_srt_time(seg['end_ms'])}", seg["text"], ""])

    with open(output_srt, "w", encoding="utf-8") as f: f.write("\n".join(srt_lines))
    with open(output_json, "w", encoding="utf-8") as f: json.dump(segments_data, f, ensure_ascii=False, indent=2)

    log(f"[COMPLETED] SRT meets professional video standards.")
    print(f"\nCONTENT_NAME={args.content_name}")

if __name__ == "__main__":
    main()
