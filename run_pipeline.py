#!/usr/bin/env python3
"""
Auto Create Video Pipeline
Run the entire pipeline from B2 to B5:

B1: Content (already available in B1-Content/*.txt)
B2: Text -> Audio (TTS)
B3: Audio -> SRT (Speech Recognition)
B4: SRT Verification (fix spelling errors)
B5: Audio + SRT + Video -> Video 16:9 & 9:16

All outputs have content name prefix to avoid overwriting.

Usage:
    python run_pipeline.py
"""

import os
import sys
import subprocess
import argparse

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = {
    "B2": os.path.join("B2-TTS", "tts.py"),
    "B3": os.path.join("B3-Create-SRT", "create_srt.py"),
    "B4": os.path.join("B4-Verify-SRT", "verify_srt.py"),
    "B5": os.path.join("B5-Create-Video", "create_video_ass.py"),
}

STEPS = ["B2", "B3", "B4", "B5"]
STEP_ALIASES = {"2": "B2", "3": "B3", "4": "B4", "5": "B5"}
STEP_CHOICES = STEPS + list(STEP_ALIASES.keys())


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def normalize_step(step: str) -> str:
    if step in STEP_ALIASES:
        return STEP_ALIASES[step]
    return step


def run_step(step: str, content_name: str) -> bool:
    """Run one step in the pipeline with content_name."""
    step = normalize_step(step)
    if step not in SCRIPTS:
        print(f"[ERROR] Unknown step '{step}'")
        return False

    script_path = os.path.join(PROJECT_DIR, SCRIPTS[step])
    if not os.path.exists(script_path):
        print(f"[ERROR] Script not found: {script_path}")
        return False

    print_header(f"Step {step}: {SCRIPTS[step]} [{content_name}]")

    cmd = [sys.executable, "-X", "utf8", script_path, "--content-name", content_name]
    result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=False)

    if result.returncode != 0:
        print(f"\n[ERROR] Step {step} failed with error code {result.returncode}")
        return False

    print(f"\n[OK] Step {step} completed!")
    return True


def check_file_exists(path: str, desc: str) -> bool:
    exists = os.path.exists(path)
    status = "✓" if exists else "✗"
    print(f"  {status} {desc}: {os.path.basename(path)}")
    return exists


def list_content_files():
    """List available content files."""
    content_dir = os.path.join(PROJECT_DIR, "B1-Content")
    if not os.path.exists(content_dir):
        return []
    return sorted([f for f in os.listdir(content_dir) if f.endswith('.txt')])


def show_status(content_name="content1"):
    """Check status of input/output files."""
    print_header("STATUS CHECK")

    files = [
        (os.path.join(PROJECT_DIR, "B1-Content", f"{content_name}.txt"), "Original Content (B1)"),
        (os.path.join(PROJECT_DIR, "B2-TTS", "export", f"{content_name}_output_audio.wav"), "Audio WAV (B2)"),
        (os.path.join(PROJECT_DIR, "B3-Create-SRT", "export", f"{content_name}_subtitles.srt"), "Raw SRT (B3)"),
        (os.path.join(PROJECT_DIR, "B4-Verify-SRT", "export", f"{content_name}_subtitles_verified.srt"), "SRT verified (B4)"),
        (os.path.join(PROJECT_DIR, "B5-Create-Video", "export", content_name, f"{content_name}_ass_16_9.mp4"), "Video 16:9 (B5)"),
        (os.path.join(PROJECT_DIR, "B5-Create-Video", "export", content_name, f"{content_name}_ass_9_16.mp4"), "Video 9:16 (B5)"),
    ]

    results = [check_file_exists(p, d) for p, d in files]
    has_content = results[0] if results else False

    # Check video library
    video_lib = os.path.join(PROJECT_DIR, "B5-Create-Video", "Library")
    if os.path.exists(video_lib):
        video_count = len([f for f in os.listdir(video_lib)
                          if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))])
        print(f"  ✓ Video library (B5): {video_count} files")
    else:
        print(f"  ✗ Video library (B5): Not found")

    print()
    return has_content


def main():
    parser = argparse.ArgumentParser(
        description="Auto Create Video Pipeline - Automatically create videos from content"
    )
    parser.add_argument(
        "--step", "-s",
        choices=STEP_CHOICES + ["ALL"],
        default="ALL",
        help="Run a specific step or ALL (default: ALL)"
    )
    parser.add_argument(
        "--content-name", default="content1",
        help="Content name (e.g. content1). Default: content1"
    )
    parser.add_argument(
        "--content-names",
        default=None,
        help="Comma-separated list of content names. E.g.: content1,content2"
    )
    parser.add_argument(
        "--all-contents",
        action="store_true",
        help="Run all .txt files in B1-Content sequentially (not concurrently)"
    )
    parser.add_argument(
        "--list-content",
        action="store_true",
        help="List available content files"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check file status"
    )
    parser.add_argument(
        "--start-from",
        choices=STEP_CHOICES,
        default=None,
        help="Run from this step to the end"
    )
    parser.add_argument(
        "--from-step",
        choices=STEP_CHOICES,
        default=None,
        help="Run from this step"
    )
    parser.add_argument(
        "--to-step",
        choices=STEP_CHOICES,
        default=None,
        help="Run up to this step"
    )

    args = parser.parse_args()

    if len(sys.argv) == 1:
        args.all_contents = True

    # List content files
    if args.list_content:
        print_header("AVAILABLE CONTENT FILES")
        for f in list_content_files():
            name = os.path.splitext(f)[0]
            print(f"  - {f}  ->  use --content-name {name}")
        return

    if args.all_contents:
        content_names = [os.path.splitext(f)[0] for f in list_content_files()]
        if not content_names:
            print("[ERROR] No .txt files in B1-Content directory.")
            sys.exit(1)
    elif args.content_names:
        content_names = [c.strip() for c in args.content_names.split(",") if c.strip()]
        if not content_names:
            print("[ERROR] --content-names is empty.")
            sys.exit(1)
    else:
        content_names = [args.content_name]

    # Check status
    if args.status:
        for name in content_names:
            show_status(name)
        return

    # Determine steps to run
    if args.from_step:
        from_step = normalize_step(args.from_step)
        to_step = normalize_step(args.to_step) if args.to_step else "B5"
        if from_step not in STEPS or to_step not in STEPS:
            print(f"[ERROR] Invalid from/to step: {args.from_step} -> {args.to_step}")
            sys.exit(1)
        if STEPS.index(from_step) > STEPS.index(to_step):
            print(f"[ERROR] from-step must be <= to-step: {args.from_step} -> {args.to_step}")
            sys.exit(1)
        steps_to_run = STEPS[STEPS.index(from_step):STEPS.index(to_step) + 1]
    elif args.start_from:
        start_from = normalize_step(args.start_from)
        steps_to_run = STEPS[STEPS.index(start_from):]
    elif args.step == "ALL":
        steps_to_run = STEPS
    else:
        steps_to_run = [normalize_step(args.step)]

    print_header("AUTO VIDEO CREATION PIPELINE")
    print(f"  Will run sequentially: {', '.join(content_names)}")
    print(f"  Steps: {', '.join(steps_to_run)}")
    print()

    completed = []
    for content_name in content_names:
        content_file = os.path.join(PROJECT_DIR, "B1-Content", f"{content_name}.txt")
        if not os.path.exists(content_file):
            print(f"[ERROR] File not found: {content_file}")
            sys.exit(1)

        print_header(f"CONTENT: {content_name}")
        show_status(content_name)

        for step in steps_to_run:
            success = run_step(step, content_name)
            if not success:
                print(f"\n[FAILED] Pipeline stopped at step {step} (content: {content_name})")
                sys.exit(1)

        output_16_9 = os.path.join(PROJECT_DIR, "B5-Create-Video", "export", content_name, f"{content_name}_ass_16_9.mp4")
        output_9_16 = os.path.join(PROJECT_DIR, "B5-Create-Video", "export", content_name, f"{content_name}_ass_9_16.mp4")
        completed.append((content_name, output_16_9, output_9_16))

    print_header("PIPELINE COMPLETED!")
    for content_name, output_16_9, output_9_16 in completed:
        print(f"  Content: {content_name}")
        if os.path.exists(output_16_9):
            print(f"    ✓ Video 16:9: {output_16_9}")
        if os.path.exists(output_9_16):
            print(f"    ✓ Video 9:16: {output_9_16}")
    print(f"\nCongratulations! Pipeline has finished successfully.")


if __name__ == "__main__":
    main()
