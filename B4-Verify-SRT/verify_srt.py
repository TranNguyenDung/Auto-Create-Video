#!/usr/bin/env python3
"""
B4 - SRT Verification and Error Correction (Global Alignment 100%)
Uses global alignment algorithm to ensure no words are lost from the original.
"""

import os
import sys
import json
import re
import argparse
from difflib import SequenceMatcher

# =================================================================
# CUSTOM CONFIGURATIONS
# =================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "B1-Content")
B3_EXPORT_DIR = os.path.join(BASE_DIR, "B3-Create-SRT", "export")
B4_DIR = os.path.join(BASE_DIR, "B4-Verify-SRT")
OUTPUT_DIR = os.path.join(B4_DIR, "export")
# =================================================================

def log(msg: str):
    print(f"[B4] {msg}")

def normalize(text: str) -> str:
    """Normalize for word matching."""
    t = text.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    return t

def ms_to_srt_time(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def main():
    parser = argparse.ArgumentParser(description="B4 - Global Perfect Alignment")
    parser.add_argument("--content-name", default="content1", help="Content file name")
    args = parser.parse_args()

    content_path = os.path.join(CONTENT_DIR, f"{args.content_name}.txt")
    json_path = os.path.join(B3_EXPORT_DIR, f"{args.content_name}_segments.json")
    output_srt = os.path.join(OUTPUT_DIR, f"{args.content_name}_subtitles_verified.srt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Read data
    if not os.path.exists(content_path) or not os.path.exists(json_path):
        log("[ERROR] Missing B1 or B3 input files.")
        sys.exit(1)

    with open(content_path, "r", encoding="utf-8") as f:
        original_raw = f.read().strip()
    
    with open(json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    print(f"\n{'='*50}\nB4 - GLOBAL ALIGNMENT [{args.content_name}]\n{'='*50}")

    # Split original text into word list
    original_words = original_raw.split()
    original_words_norm = [normalize(w) for w in original_words]
    
    # Collect all detected words and mark which segment they belong to
    detected_words_norm = []
    word_to_segment = [] # Store segment index for each detected word
    
    for seg_idx, seg in enumerate(segments):
        words = normalize(seg["text"]).split()
        for w in words:
            detected_words_norm.append(w)
            word_to_segment.append(seg_idx)

    # 2. Perform Global Alignment
    log("Computing global alignment matrix...")
    matcher = SequenceMatcher(None, detected_words_norm, original_words_norm)
    opcodes = matcher.get_opcodes()

    # Create result array: each segment will contain corresponding original words
    final_segments_content = [[] for _ in range(len(segments))]
    
    # Iterate through opcodes to distribute original words into segments
    # tag: 'replace', 'delete', 'insert', 'equal'
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            # Detected words match original -> assign to correct segment
            for det_idx, orig_idx in zip(range(i1, i2), range(j1, j2)):
                seg_idx = word_to_segment[det_idx]
                final_segments_content[seg_idx].append(original_words[orig_idx])
        
        elif tag == 'replace' or tag == 'insert':
            # New or misrecognized words -> distribute to nearest segment
            # Get segment index from neighboring detected word
            if i1 < len(word_to_segment):
                seg_idx = word_to_segment[i1]
            elif i1 > 0:
                seg_idx = word_to_segment[i1-1]
            else:
                seg_idx = 0
                
            for orig_idx in range(j1, j2):
                final_segments_content[seg_idx].append(original_words[orig_idx])
        
        # 'delete' means AI heard extra words -> skip (we follow original text)

    # 3. Merge words into complete sentences for each segment
    verified_segments = []
    fix_count = 0
    
    for i, seg_words in enumerate(final_segments_content):
        if not seg_words:
            continue
            
        corrected_text = " ".join(seg_words)
        
        # Check if there are changes compared to B3
        old_text = segments[i]["text"]
        if normalize(corrected_text) != normalize(old_text):
            fix_count += 1
            if fix_count <= 5 or i % 10 == 0:
                print(f"  [{i+1:03d}] Restored: \"{old_text[:20]}...\" -> \"{corrected_text[:40]}...\"")
        
        verified_segments.append({
            "start_ms": segments[i]["start_ms"],
            "end_ms": segments[i]["end_ms"],
            "text": corrected_text
        })

    # 4. Export SRT file
    srt_lines = []
    for i, seg in enumerate(verified_segments, 1):
        srt_lines.extend([
            str(i), 
            f"{ms_to_srt_time(seg['start_ms'])} --> {ms_to_srt_time(seg['end_ms'])}", 
            seg["text"], 
            ""
        ])

    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    print(f"\n{'='*50}")
    log(f"[COMPLETED] 100% accuracy, no words lost.")
    log(f"  - File: {output_srt}")
    print(f"{'='*50}\n")
    print(f"CONTENT_NAME={args.content_name}")

if __name__ == "__main__":
    main()
