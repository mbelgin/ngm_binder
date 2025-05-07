#!/usr/bin/env python3
"""
Bind National Geographic JPG scans into a single PDF file.

Usage:

  # Batch process all folders recursively under the given path
  new_ngb_binder.py --all "/path/to/root" --output /path/to/output --jobs 4

  # Convert a single issue by date (matches folder with prefix)
  new_ngb_binder.py "/path/to/root" 199408

  # Convert a single folder regardless of name
  new_ngb_binder.py --dir "/path/to/exact/folder"

Arguments:
  --all ROOT            Root path to scan recursively for candidate folders
  --output OUTPUTDIR    Output directory for PDFs (default: current directory)
  --jobs JOBS           Number of parallel threads (default: 1)
  --dir DIR             Convert a specific folder (no pattern matching)
  src                   Root path for single-issue mode
  yyyymm                Issue identifier (e.g., 199408)
"""

import os
import re
import sys
import time
import argparse
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

def extract_yyyymm(foldername):
    match = re.search(r'(\d{6})', os.path.basename(foldername))
    return match.group(1) if match else None

def fast_find_dirs(root):
    found_dirs = []
    for entry in os.scandir(root):
        if entry.is_dir():
            found_dirs.append(entry.path)
            found_dirs.extend(fast_find_dirs(entry.path))
    return found_dirs

def is_valid_folder(folder):
    try:
        return any(f.name.lower().endswith(".jpg") for f in Path(folder).iterdir())
    except Exception:
        return False

def get_jpg_files(folder, yyyymm=None):
    folder = Path(folder)
    jpgs = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".jpg"])
    page_files = []
    extra_files = []
    for f in jpgs:
        name = f.name
        if name.startswith("NGM_"):
            page_files.append(str(f))
        else:
            extra_files.append(str(f))
    return page_files + extra_files

def build_pdf(jpg_list, output_path, fail_log=None):
    temp_output = output_path + ".chk"
    image_list = []
    failed_files = []
    for f in jpg_list:
        try:
            img = Image.open(f).convert("RGB")
            image_list.append(img)
        except:
            failed_files.append(f)
    if image_list:
        os.makedirs(os.path.dirname(temp_output), exist_ok=True)
        try:
            image_list[0].save(temp_output, save_all=True, append_images=image_list[1:], format="PDF")
            os.rename(temp_output, output_path)
        except Exception as e:
            failed_files.append(f"WRITE_ERROR: {e}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
    if fail_log and failed_files:
        with open(fail_log, "a") as f:
            for path in failed_files:
                f.write(path + "\n")
    return failed_files

def print_status(index, total, folder, status):
    print(f"Processed {index}/{total} - [{os.path.basename(folder)}] - Status: {status}")

def process_folder(index, total, folder, output_dir, fail_log):
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print_status(index, total, folder, "⏭️ Skipped")
        return
    output_file = f"NGM_{yyyymm}.pdf"
    output_path = os.path.join(output_dir, output_file)

    if os.path.exists(output_path):
        print_status(index, total, folder, "🟦 Existing")
        return
    if os.path.exists(output_path + ".chk"):
        os.remove(output_path + ".chk")

    jpgs = get_jpg_files(folder, yyyymm)
    if not jpgs:
        print_status(index, total, folder, "⏭️ Skipped")
        return

    failed = build_pdf(jpgs, output_path, fail_log=fail_log)
    print_status(index, total, folder, "❌ Failed" if failed else "✅ Converted")

def run_batch(root, output_dir, jobs):
    print(f"Scanning directory tree under '{root}'... please wait")
    start = time.time()
    candidates = fast_find_dirs(root)
    duration = time.time() - start
    print(f"Found {len(candidates)} folders in {duration:.2f} seconds.\n")

    folders = [f for f in candidates if is_valid_folder(f)]
    total = len(folders)
    fail_log = os.path.join(output_dir, "failed.log")
    if os.path.exists(fail_log):
        os.remove(fail_log)

    with ThreadPoolExecutor(max_workers=jobs or 1) as executor:
        futures = {
            executor.submit(process_folder, i+1, total, folder, output_dir, fail_log): folder
            for i, folder in enumerate(folders)
        }
        for future in as_completed(futures):
            _ = future.result()

def process_single_folder(folder, output_dir):
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print(f"Cannot extract YYYYMM from folder name: {folder}")
        return
    output_file = f"NGM_{yyyymm}.pdf"
    output_path = os.path.join(output_dir, output_file)
    fail_log = os.path.join(output_dir, "failed.log")
    if os.path.exists(fail_log):
        os.remove(fail_log)
    jpgs = get_jpg_files(folder, yyyymm)
    failed = build_pdf(jpgs, output_path, fail_log=fail_log)
    print("✅ Done" if not failed else "❌ Failed (see failed.log)")

def main():
    parser = argparse.ArgumentParser(description="Bind National Geographic JPG scans into a single PDF.")
    parser.add_argument("--all", action="store_true", help="Batch convert all folders under root")
    parser.add_argument("--output", metavar="OUTPUTDIR", default=os.getcwd(), help="Output directory")
    parser.add_argument("--jobs", type=int, default=1, help="Number of threads for parallel processing")
    parser.add_argument("--dir", metavar="DIR", help="Exact folder path to convert")
    parser.add_argument("src", nargs="?", help="Root path (for --all or date mode)")
    parser.add_argument("yyyymm", nargs="?", help="Date-based folder search (e.g. 199408)")
    args = parser.parse_args()

    if args.all:
        if not args.src:
            print("Error: --all requires a source root path.")
            sys.exit(1)
        run_batch(args.src, args.output, args.jobs)
        return

    if args.dir:
        process_single_folder(args.dir, args.output)
        return

    if args.src and args.yyyymm:
        print(f"Looking for issue folder starting with {args.yyyymm}...")
        candidates = [
            str(p) for p in Path(args.src).rglob(f"{args.yyyymm}*")
            if p.is_dir()
        ]
        if not candidates:
            print("No matching folders found.")
            return
        if len(candidates) == 1:
            folder = candidates[0]
        else:
            for i, path in enumerate(candidates):
                print(f"{i+1}: {path}")
            choice = int(input("Select folder number: "))
            folder = candidates[choice - 1]
        process_single_folder(folder, args.output)
        return

    parser.print_help()

if __name__ == "__main__":
    main()

