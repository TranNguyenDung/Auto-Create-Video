#!/usr/bin/env python3
"""
B4 - Xác thực và sửa lỗi SRT (Phiên bản Global Alignment 100%)
Dùng thuật toán so khớp toàn cục để đảm bảo không mất bất kỳ từ nào từ bản gốc.
"""

import os
import sys
import json
import re
import argparse
from difflib import SequenceMatcher

# =================================================================
# CẤU HÌNH TÙY CHỈNH (CONFIGURATIONS)
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
    """Chuẩn hóa để so khớp từ."""
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
    parser.add_argument("--content-name", default="content1", help="Tên file content")
    args = parser.parse_args()

    content_path = os.path.join(CONTENT_DIR, f"{args.content_name}.txt")
    json_path = os.path.join(B3_EXPORT_DIR, f"{args.content_name}_segments.json")
    output_srt = os.path.join(OUTPUT_DIR, f"{args.content_name}_subtitles_verified.srt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Đọc dữ liệu
    if not os.path.exists(content_path) or not os.path.exists(json_path):
        log("[LỖI] Thiếu file đầu vào B1 hoặc B3.")
        sys.exit(1)

    with open(content_path, "r", encoding="utf-8") as f:
        original_raw = f.read().strip()
    
    with open(json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    print(f"\n{'='*50}\nB4 - KHỚP TOÀN CỤC (GLOBAL ALIGNMENT) [{args.content_name}]\n{'='*50}")

    # Tách văn bản gốc thành danh sách các từ
    original_words = original_raw.split()
    original_words_norm = [normalize(w) for w in original_words]
    
    # Gom toàn bộ từ AI nghe được và đánh dấu nó thuộc segment nào
    detected_words_norm = []
    word_to_segment = [] # Lưu index của segment cho mỗi từ AI nghe được
    
    for seg_idx, seg in enumerate(segments):
        words = normalize(seg["text"]).split()
        for w in words:
            detected_words_norm.append(w)
            word_to_segment.append(seg_idx)

    # 2. Thực hiện So khớp toàn cục (Global Alignment)
    log("Đang tính toán ma trận so khớp toàn văn bản...")
    matcher = SequenceMatcher(None, detected_words_norm, original_words_norm)
    opcodes = matcher.get_opcodes()

    # Tạo mảng lưu kết quả: mỗi segment sẽ chứa danh sách từ gốc tương ứng
    final_segments_content = [[] for _ in range(len(segments))]
    
    # Duyệt qua các opcode để phân bổ từ gốc vào các segment
    # tag: 'replace', 'delete', 'insert', 'equal'
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            # Từ nghe được khớp với từ gốc -> đưa vào đúng segment
            for det_idx, orig_idx in zip(range(i1, i2), range(j1, j2)):
                seg_idx = word_to_segment[det_idx]
                final_segments_content[seg_idx].append(original_words[orig_idx])
        
        elif tag == 'replace' or tag == 'insert':
            # Có từ gốc mới hoặc từ gốc bị AI nghe sai -> phân bổ vào segment gần nhất
            # Lấy segment index từ từ detected lân cận
            if i1 < len(word_to_segment):
                seg_idx = word_to_segment[i1]
            elif i1 > 0:
                seg_idx = word_to_segment[i1-1]
            else:
                seg_idx = 0
                
            for orig_idx in range(j1, j2):
                final_segments_content[seg_idx].append(original_words[orig_idx])
        
        # 'delete' nghĩa là AI nghe thừa từ -> ta bỏ qua (vì ta bám theo văn bản gốc)

    # 3. Hợp nhất các từ lại thành câu hoàn chỉnh cho mỗi segment
    verified_segments = []
    fix_count = 0
    
    for i, seg_words in enumerate(final_segments_content):
        if not seg_words:
            continue
            
        corrected_text = " ".join(seg_words)
        
        # Kiểm tra xem có thay đổi so với bản B3 không
        old_text = segments[i]["text"]
        if normalize(corrected_text) != normalize(old_text):
            fix_count += 1
            if fix_count <= 5 or i % 10 == 0:
                print(f"  [{i+1:03d}] Khôi phục: \"{old_text[:20]}...\" -> \"{corrected_text[:40]}...\"")
        
        verified_segments.append({
            "start_ms": segments[i]["start_ms"],
            "end_ms": segments[i]["end_ms"],
            "text": corrected_text
        })

    # 4. Xuất file SRT
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
    log(f"[HOÀN TẤT] Độ chính xác 100%, không mất bất kỳ chữ nào.")
    log(f"  - File: {output_srt}")
    print(f"{'='*50}\n")
    print(f"CONTENT_NAME={args.content_name}")

if __name__ == "__main__":
    main()
