#!/usr/bin/env python3
"""
Bind National Geographic JPG scans into a single PDF file.

Usage modes:

1. Convert *all issues* under a root directory:
   ./ngb_binder.py --all ROOT --output OUTPUTDIR --jobs N

2. Convert a *specific folder* with JPGs (skip discovery):
   ./ngb_binder.py --dir /exact/path/to/folder --output OUTPUTDIR

3. Convert a *single issue* by date from a root folder:
   ./ngb_binder.py ROOT YYYYMM --output OUTPUTDIR

Notes:
- .pdf.chk files are used as checkpoints to avoid corrupt output.
- Extra (non-standard) JPGs in each issue folder are added after core pages.
- Folders that don't match the YYYYMM pattern are skipped.
- Existing PDFs are not re-generated.

Status codes:
✅ = Converted, ⏭️ = Skipped, 🟦 = Already exists, ❌ = Failed
"""

import os
import sys
import argparse
import re
import time
from pathlib import Path
from PIL import Image
from multiprocessing import Pool

SYMBOLS = {
    'converted': '✅',
    'skipped': '⏭️',
    'exists': '🟦',
    'failed': '❌'
}

def extract_yyyymm(foldername):
    match = re.search(r'(\d{6})', os.path.basename(foldername))
    return match.group(1) if match else None

def fast_find_dirs(root):
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        found.append(current)
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir():
                        stack.append(entry.path)
        except PermissionError:
            continue
    return found

def get_jpg_files(folder, yyyymm):
    core_pattern = re.compile(rf'^NGM_{yyyymm[:4]}_{yyyymm[4:6]}_[0-9]{{3}}[A-Z]?_[0-9]\.jpg$', re.IGNORECASE)
    page_files, extra_files = [], []
    try:
        for file in sorted(os.listdir(folder)):
            full = os.path.join(folder, file)
            if not os.path.isfile(full):
                continue
            if file.lower().endswith(".jpg"):
                (page_files if core_pattern.match(file) else extra_files).append(full)
    except Exception:
        return [], []
    return page_files + extra_files, yyyymm

def build_pdf(jpgs, output_path, temp_path):
    images = []
    for jpg in jpgs:
        try:
            img = Image.open(jpg).convert("RGB")
            images.append(img)
        except:
            continue
    if not images:
        return False
    try:
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        images[0].save(temp_path, save_all=True, append_images=images[1:], format="PDF")
        os.rename(temp_path, output_path)
        return True
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def process_folder(args):
    index, total, folder, output_dir = args
    folder_name = os.path.basename(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        return index, total, folder_name, 'skipped'

    output_pdf = os.path.join(output_dir, f'NGM_{yyyymm}.pdf')
    temp_pdf = output_pdf + ".chk"

    if os.path.exists(output_pdf):
        return index, total, folder_name, 'exists'

    jpgs, _ = get_jpg_files(folder, yyyymm)
    if not jpgs:
        return index, total, folder_name, 'skipped'

    success = build_pdf(jpgs, output_pdf, temp_pdf)
    return index, total, folder_name, 'converted' if success else 'failed'

def print_status(index, total, folder, status):
    print(f"Processed {index + 1}/{total} - [{folder}] - Status: {SYMBOLS[status]}")

def run_batch(root, output_dir, jobs):
    start = time.time()
    print(f"Scanning directory tree under '{root}'... please wait")
    all_dirs = [d for d in fast_find_dirs(root) if os.path.isdir(d)]
    print(f"Found {len(all_dirs)} folders in {time.time() - start:.2f} seconds.\n")

    args_list = [(i, len(all_dirs), folder, output_dir) for i, folder in enumerate(all_dirs)]
    if jobs == 1:
        for args in args_list:
            res = process_folder(args)
            print_status(*res)
    else:
        with Pool(processes=jobs) as pool:
            for res in pool.imap_unordered(process_folder, args_list):
                print_status(*res)

def run_by_dir(folder, output_dir):
    folder = os.path.abspath(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print(f"❌ Error: Folder name does not contain YYYYMM: {folder}")
        return
    jpgs, _ = get_jpg_files(folder, yyyymm)
    if not jpgs:
        print(f"❌ Error: No JPG files found in {folder}")
        return
    output_pdf = os.path.join(output_dir, f'NGM_{yyyymm}.pdf')
    temp_pdf = output_pdf + ".chk"
    if os.path.exists(output_pdf):
        print(f"🟦 Exists: {output_pdf}")
        return
    if build_pdf(jpgs, output_pdf, temp_pdf):
        print(f"✅ Created: {output_pdf}")
    else:
        print(f"❌ Failed: {output_pdf}")

def run_by_date(root, yyyymm, output_dir):
    matches = []
    for dirpath, dirnames, _ in os.walk(root):
        for d in dirnames:
            if d.startswith(yyyymm):
                matches.append(os.path.join(dirpath, d))
    if not matches:
        print(f"❌ No folder found for issue {yyyymm}")
        return
    if len(matches) > 1:
        print("Multiple matches found:")
        for i, path in enumerate(matches):
            print(f"{i + 1}: {path}")
        sel = int(input("Select one: ")) - 1
        folder = matches[sel]
    else:
        folder = matches[0]
    run_by_dir(folder, output_dir)

def main():
    parser = argparse.ArgumentParser(description="Bind National Geographic JPG scans into a single PDF.")
    parser.add_argument("--all", action="store_true", help="Convert all valid subfolders under ROOT")
    parser.add_argument("--output", metavar="OUTPUTDIR", default=os.getcwd(), help="Output directory for PDFs")
    parser.add_argument("--jobs", type=int, default=1, help="Number of parallel jobs to run (default: 1)")
    parser.add_argument("--dir", metavar="DIR", help="Exact folder to bind (no discovery)")
    parser.add_argument("src", nargs="?", help="Root directory to search for specific issue")
    parser.add_argument("yyyymm", nargs="?", help="Issue date in YYYYMM format")
    args = parser.parse_args()

    if args.all and args.src:
        run_batch(args.src, args.output, args.jobs)
    elif args.dir:
        run_by_dir(args.dir, args.output)
    elif args.src and args.yyyymm:
        run_by_date(args.src, args.yyyymm, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

