#!/usr/bin/env python3
import os
import re
import sys
import argparse
import time
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

SYMBOLS = {
    'todo': '🔘',
    'skip': '⏭️',
    'done': '✅',
    'fail': '❌',
    'exist': '🟦'
}

def convert_cng_to_jpg(src_path, delete=False):
    jpg_path = src_path.with_suffix('.jpg')
    try:
        with open(src_path, 'rb') as fin, open(jpg_path, 'wb') as fout:
            fout.write(bytearray((b ^ 239) for b in fin.read()))
        if delete:
            os.remove(src_path)
        return jpg_path
    except Exception:
        return None

def fast_find_dirs(root):
    result = []
    for dirpath, dirnames, _ in os.walk(root):
        result.append(dirpath)
    return result

def extract_yyyymm(foldername):
    match = re.search(r'(\d{6})', os.path.basename(foldername))
    if match:
        return match.group(1)
    return None

def get_image_files(folder, yyyymm, delete_cng=False):
    files = []
    extras = []
    for entry in sorted(Path(folder).iterdir()):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        name = entry.name
        if ext == '.jpg' and name.lower().startswith('ngm_'):
            files.append(entry)
        elif ext == '.cng' and name.lower().startswith('ngm_'):
            jpg_path = convert_cng_to_jpg(entry, delete=delete_cng)
            if jpg_path:
                files.append(jpg_path)
        elif ext in ['.jpg', '.cng']:
            if ext == '.cng':
                jpg_path = convert_cng_to_jpg(entry, delete=delete_cng)
                if jpg_path:
                    extras.append(jpg_path)
            else:
                extras.append(entry)
    return files + extras

def build_pdf(images, output_path, fail_log=None):
    temp_output = output_path + ".chk"
    image_objs = []
    failed = []
    for f in images:
        try:
            with Image.open(f) as im:
                image_objs.append(im.convert("RGB"))
        except Exception:
            failed.append(str(f))
    if image_objs:
        os.makedirs(os.path.dirname(temp_output), exist_ok=True)
        try:
            image_objs[0].save(temp_output, save_all=True, append_images=image_objs[1:], format='PDF')
            os.rename(temp_output, output_path)
        except Exception as e:
            failed.append(f"WRITE_ERROR: {e}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
    if fail_log and failed:
        with open(fail_log, "a") as f:
            for err in failed:
                f.write(err + "\n")
    return failed

def print_status(index, total, name, status):
    print(f"Processed {index + 1}/{total} - [{name}] - Status: {status}")

def process_folder(index, folder, total, output_dir, delete_cng):
    name = os.path.basename(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print_status(index, total, name, SYMBOLS['skip'])
        return
    output_file = os.path.join(output_dir, f'NGM_{yyyymm}.pdf')
    temp_file = output_file + ".chk"
    if os.path.exists(output_file):
        print_status(index, total, name, SYMBOLS['exist'])
        return
    if os.path.exists(temp_file):
        os.remove(temp_file)

    images = get_image_files(folder, yyyymm, delete_cng=delete_cng)
    if not images:
        print_status(index, total, name, SYMBOLS['skip'])
        return

    failed = build_pdf(images, output_file)
    print_status(index, total, name, SYMBOLS['fail' if failed else 'done'])

def run_batch(root, output_dir, jobs, delete_cng):
    print(f"Scanning directory tree under '{root}'... please wait")
    t0 = time.time()
    folders = fast_find_dirs(root)
    print(f"Found {len(folders)} folders in {time.time() - t0:.2f} seconds.\n")

    os.makedirs(output_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for i, folder in enumerate(folders):
            executor.submit(process_folder, i, folder, len(folders), output_dir, delete_cng)

def get_target_folder(rootdir, yyyymm):
    print(f"Looking for issue {yyyymm} in {rootdir}...")
    candidates = []
    for path in Path(rootdir).rglob(f'{yyyymm}*'):
        if path.is_dir():
            candidates.append(str(path))
    if not candidates:
        print("No matching folders found.")
        sys.exit(1)
    elif len(candidates) == 1:
        return candidates[0]
    else:
        for i, path in enumerate(candidates):
            print(f"{i+1}: {path}")
        choice = int(input("Select one: "))
        return candidates[choice - 1]

def main():
    parser = argparse.ArgumentParser(description="Bind National Geographic JPG scans into a PDF.")
    parser.add_argument('--all', action='store_true', help='Scan all subfolders and convert')
    parser.add_argument('--output', default=os.getcwd(), help='Output directory for PDFs')
    parser.add_argument('--jobs', type=int, default=4, help='Parallel jobs (default: 4)')
    parser.add_argument('--delete', '-r', action='store_true', help='Delete CNGs after successful conversion')
    parser.add_argument('--dir', metavar='DIR', help='Exact folder to convert (no guessing)')
    parser.add_argument('src', nargs='?', help='Root directory or specific folder')
    parser.add_argument('yyyymm', nargs='?', help='Date in YYYYMM format for issue-based conversion')
    args = parser.parse_args()

    if args.all:
        run_batch(args.src, args.output, args.jobs, args.delete)
    elif args.dir:
        folder = args.dir
        yyyymm = extract_yyyymm(folder)
        if not yyyymm:
            print(f"Invalid directory format: {folder}")
            sys.exit(1)
        process_folder(0, folder, 1, args.output, args.delete)
    elif args.src and args.yyyymm:
        folder = get_target_folder(args.src, args.yyyymm)
        process_folder(0, folder, 1, args.output, args.delete)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

