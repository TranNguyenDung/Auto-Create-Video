#!/usr/bin/env python3
"""
B2 - Text-to-Speech (OmniVoice)
Convert text to audio, with Voice Cloning support.
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
# CUSTOM CONFIGURATIONS
# =================================================================
MODEL_NAME = "k2-fsa/OmniVoice"
SAMPLE_RATE = 24000

# Device configuration
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "B1-Content")
B2_DIR = os.path.join(BASE_DIR, "B2-TTS")
OUTPUT_DIR = os.path.join(B2_DIR, "export")
VOICE_SAMPLE_DIR = os.path.join(B2_DIR, "VoiceSample")
MODEL_DIR = os.path.join(B2_DIR, "models")  # Save model here

# Voice Cloning reference files
REF_AUDIO = os.path.join(VOICE_SAMPLE_DIR, "web_20260513_234651.wav")
REF_TEXT_FILE = os.path.join(VOICE_SAMPLE_DIR, "web_20260513_234651.txt")
# =================================================================

def log(msg: str):
    print(f"[B2] {msg}")

def check_for_updates(model_name: str, local_dir: str):
    """Check and update model from Hugging Face."""
    try:
        from huggingface_hub import snapshot_download, model_info
        log(f"Checking model version: {model_name}...")
        
        info = model_info(model_name)
        latest_commit = info.sha
        
        version_file = os.path.join(local_dir, "version.txt")
        current_commit = ""
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                current_commit = f.read().strip()
        
        if current_commit != latest_commit:
            log(f"New version detected. Downloading/updating model to {local_dir}...")
            snapshot_download(
                repo_id=model_name,
                local_dir=local_dir,
                local_dir_use_symlinks=False
            )
            with open(version_file, "w") as f:
                f.write(latest_commit)
            log("Update complete.")
        else:
            log("Model is already up to date.")
    except Exception as e:
        log(f"[WARNING] Cannot check for updates: {e}")

def read_file(path: str) -> str:
    """Read text file content."""
    if not os.path.exists(path):
        log(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def generate_audio(text: str, model, ref_audio=None, ref_text=None) -> np.ndarray:
    """Generate audio from text using OmniVoice model."""
    kwargs = {"text": text}
    if ref_audio and ref_text:
        kwargs.update({"ref_audio": ref_audio, "ref_text": ref_text})
    
    try:
        audios = model.generate(**kwargs)
        return audios[0] if audios else None
    except Exception as e:
        log(f"[ERROR] Generation failed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="B2 - TTS OmniVoice")
    parser.add_argument("--content-name", default="content1", help="Content file name (without .txt)")
    args = parser.parse_args()

    # Initialize paths
    content_path = os.path.join(CONTENT_DIR, f"{args.content_name}.txt")
    output_wav = os.path.join(OUTPUT_DIR, f"{args.content_name}_output_audio.wav")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*50}\nB2 - TTS OMNIVOICE [{args.content_name}]\n{'='*50}")

    # 1. Read content & Voice Sample
    content = read_file(content_path)
    ref_text = read_file(REF_TEXT_FILE) if os.path.exists(REF_TEXT_FILE) else None
    has_voice_ref = ref_text and os.path.exists(REF_AUDIO)
    
    log(f"Read content ({len(content)} characters)")
    if has_voice_ref:
        log(f"Using Voice Cloning: {os.path.basename(REF_AUDIO)}")
    else:
        log("[WARNING] No voice sample available, using Auto mode.")

    # 2. Check and Load Model
    os.makedirs(MODEL_DIR, exist_ok=True)
    check_for_updates(MODEL_NAME, MODEL_DIR)

    log(f"Loading model from {MODEL_DIR} on {DEVICE}...")
    start_load = time.time()
    model = OmniVoice.from_pretrained(
        MODEL_NAME, 
        device_map=DEVICE, 
        dtype=DTYPE,
        cache_dir=MODEL_DIR
    )
    log(f"Model ready ({time.time() - start_load:.1f}s)")

    # 3. Process TTS (Send full text at once to avoid concatenation errors)
    log("Generating speech (processing entire content)...")
    
    combined = generate_audio(content, model, REF_AUDIO if has_voice_ref else None, ref_text)
    
    if combined is None:
        log("[ERROR] Failed to generate audio!")
        sys.exit(1)

    # 4. Save result
    sf.write(output_wav, combined, SAMPLE_RATE)
    
    duration = len(combined) / SAMPLE_RATE
    log(f"[COMPLETED] Audio: {output_wav}")
    log(f"  - Duration: {duration:.2f}s | Size: {os.path.getsize(output_wav)/(1024*1024):.1f}MB")

    # 5. Clean up GPU
    del model
    torch.cuda.empty_cache()
    print(f"\nCONTENT_NAME={args.content_name}")


if __name__ == "__main__":
    main()
