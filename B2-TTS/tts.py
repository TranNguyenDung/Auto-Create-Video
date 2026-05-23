#!/usr/bin/env python3
"""
B2 - Text-to-Speech (OmniVoice)
Chuyển text thành audio, hỗ trợ Voice Cloning.
"""

import os
import sys
import time
import argparse
import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

# =================================================================
# CẤU HÌNH TÙY CHỈNH (CONFIGURATIONS)
# =================================================================
MODEL_NAME = "k2-fsa/OmniVoice"
SAMPLE_RATE = 24000
LANGUAGE = "vi"    # Ngôn ngữ mặc định

# Cấu hình thiết bị (Device config)
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32

# Đường dẫn (Paths)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "B1-Content")
B2_DIR = os.path.join(BASE_DIR, "B2-TTS")
OUTPUT_DIR = os.path.join(B2_DIR, "export")
VOICE_SAMPLE_DIR = os.path.join(B2_DIR, "VoiceSample")
MODEL_DIR = os.path.join(B2_DIR, "models")  # Lưu model tại đây

# File mẫu cho Voice Cloning (Reference files)
REF_AUDIO = os.path.join(VOICE_SAMPLE_DIR, "web_20260513_234651.wav")
REF_TEXT_FILE = os.path.join(VOICE_SAMPLE_DIR, "web_20260513_234651.txt")
# =================================================================

def log(msg: str):
    print(f"[B2] {msg}")

def check_for_updates(model_name: str, local_dir: str):
    """Kiểm tra và cập nhật model từ Hugging Face."""
    try:
        from huggingface_hub import snapshot_download, model_info
        log(f"Kiểm tra phiên bản model: {model_name}...")
        
        info = model_info(model_name)
        latest_commit = info.sha
        
        version_file = os.path.join(local_dir, "version.txt")
        current_commit = ""
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                current_commit = f.read().strip()
        
        if current_commit != latest_commit:
            log(f"Phát hiện phiên bản mới. Đang tải/cập nhật model về {local_dir}...")
            snapshot_download(
                repo_id=model_name,
                local_dir=local_dir,
                local_dir_use_symlinks=False
            )
            with open(version_file, "w") as f:
                f.write(latest_commit)
            log("Cập nhật hoàn tất.")
        else:
            log("Model đã ở phiên bản mới nhất.")
    except Exception as e:
        log(f"[CẢNH BÁO] Không thể kiểm tra cập nhật: {e}")

def read_file(path: str) -> str:
    """Đọc nội dung file text."""
    if not os.path.exists(path):
        log(f"[LỖI] Không tìm thấy file: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def generate_audio(text: str, model, ref_audio=None, ref_text=None) -> np.ndarray:
    """Tạo audio từ text sử dụng model OmniVoice."""
    kwargs = {"text": text}
    if ref_audio and ref_text:
        kwargs.update({"ref_audio": ref_audio, "ref_text": ref_text})
    
    try:
        audios = model.generate(**kwargs)
        return audios[0] if audios else None
    except Exception as e:
        log(f"[LỖI] Generate thất bại: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="B2 - TTS OmniVoice")
    parser.add_argument("--content-name", default="content1", help="Tên file content (không gồm .txt)")
    args = parser.parse_args()

    # Khởi tạo đường dẫn
    content_path = os.path.join(CONTENT_DIR, f"{args.content_name}.txt")
    output_wav = os.path.join(OUTPUT_DIR, f"{args.content_name}_output_audio.wav")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*50}\nB2 - TTS OMNIVOICE [{args.content_name}]\n{'='*50}")

    # 1. Đọc nội dung & Voice Sample
    content = read_file(content_path)
    ref_text = read_file(REF_TEXT_FILE) if os.path.exists(REF_TEXT_FILE) else None
    has_voice_ref = ref_text and os.path.exists(REF_AUDIO)
    
    log(f"Đã đọc content ({len(content)} ký tự)")
    if has_voice_ref:
        log(f"Sử dụng Voice Cloning: {os.path.basename(REF_AUDIO)}")
    else:
        log("[CẢNH BÁO] Không có voice mẫu, dùng chế độ Auto.")

    # 2. Kiểm tra và Load Model
    os.makedirs(MODEL_DIR, exist_ok=True)
    check_for_updates(MODEL_NAME, MODEL_DIR)

    log(f"Đang tải model từ {MODEL_DIR} lên {DEVICE}...")
    start_load = time.time()
    model = OmniVoice.from_pretrained(
        MODEL_NAME, 
        device_map=DEVICE, 
        dtype=DTYPE,
        cache_dir=MODEL_DIR
    )
    log(f"Model sẵn sàng ({time.time() - start_load:.1f}s)")

    # 3. Xử lý TTS (Gửi toàn bộ text một lần để tránh lỗi nối âm)
    log("Đang tạo giọng nói (Xử lý toàn bộ nội dung)...")
    
    combined = generate_audio(content, model, REF_AUDIO if has_voice_ref else None, ref_text)
    
    if combined is None:
        log("[LỖI] Không tạo được audio!")
        sys.exit(1)

    # 4. Lưu kết quả
    sf.write(output_wav, combined, SAMPLE_RATE)
    
    duration = len(combined) / SAMPLE_RATE
    log(f"[HOÀN TẤT] Audio: {output_wav}")
    log(f"  - Thời lượng: {duration:.2f}s | Size: {os.path.getsize(output_wav)/(1024*1024):.1f}MB")

    # 5. Dọn dẹp GPU
    del model
    torch.cuda.empty_cache()
    print(f"\nCONTENT_NAME={args.content_name}")


if __name__ == "__main__":
    main()
