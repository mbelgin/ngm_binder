#!/usr/bin/env python3
import os
import re
import sys
import time
import shutil
import uuid
import argparse
import tempfile
from pathlib import Path
from PIL import Image
from pytesseract import image_to_pdf_or_hocr
from concurrent.futures import ThreadPoolExecutor
import pikepdf

SYMBOLS = {
    'skip': '⏭️',
    'done': '✅',
    'fail': '❌',
    'exist': '🟦',
    'ocr': '🔤'
}

def fast_find_dirs(root):
    result = []
    for dirpath, _, _ in os.walk(root):
        result.append(dirpath)
    return result

def extract_yyyymm(foldername):
    match = re.search(r'(\d{6})', os.path.basename(foldername))
    return match.group(1) if match else None

def convert_cng_to_jpg(src_path, delete=False):
    dst_path = src_path.with_suffix('.jpg')
    try:
        with open(src_path, 'rb') as fin, open(dst_path, 'wb') as fout:
            fout.write(bytearray((b ^ 239) for b in fin.read()))
        if delete:
            os.remove(src_path)
        return dst_path
    except Exception:
        return None

def get_image_files(folder_path, delete_cng=False):
    main_pages = []
    extras = []
    seen = set()

    for entry in sorted(Path(folder_path).iterdir()):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        name = entry.name
        stem = entry.stem.lower()
        if stem in seen:
            continue

        def add_file(p, is_main):
            if is_main:
                main_pages.append(p)
            else:
                extras.append(p)
            seen.add(p.stem.lower())

        if ext == '.jpg':
            add_file(entry, name.lower().startswith('ngm_'))
        elif ext == '.cng':
            converted = convert_cng_to_jpg(entry, delete=delete_cng)
            if converted and converted.stem.lower() not in seen:
                add_file(converted, converted.name.lower().startswith('ngm_'))

    return sorted(main_pages) + sorted(extras)

def ocr_images_to_pdf_parts(image_list, tempdir, verbose=False):
    output_parts = []
    for i, img in enumerate(image_list):
        pdf_path = os.path.join(tempdir, f"{i:03}.pdf")
        try:
            pdf_bytes = image_to_pdf_or_hocr(str(img), extension='pdf')
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)
            output_parts.append(pdf_path)
        except Exception as e:
            if verbose:
                print(f"[OCR FAIL] {img} -> {e}")
            raise
    return output_parts

def build_pdf(images, output_path, ocr=False, verbose=False):
    temp_output = output_path + ".chk"
    os.makedirs(os.path.dirname(temp_output), exist_ok=True)

    if ocr:
        tmp_ocr_dir = os.path.join(os.path.dirname(output_path), f"ocr_{uuid.uuid4().hex[:8]}")
        os.makedirs(tmp_ocr_dir, exist_ok=True)
        try:
            pdf_parts = ocr_images_to_pdf_parts(images, tmp_ocr_dir, verbose)
            with pikepdf.Pdf.new() as final_pdf:
                for part in pdf_parts:
                    final_pdf.pages.extend(pikepdf.Pdf.open(part).pages)
                final_pdf.save(temp_output)
            shutil.rmtree(tmp_ocr_dir)
        except Exception as e:
            if verbose:
                print(f"[WRITE ERROR] {e}")
            return [str(e)]
    else:
        try:
            image_objs = [Image.open(f).convert("RGB") for f in images]
            image_objs[0].save(temp_output, save_all=True, append_images=image_objs[1:], format='PDF')
        except Exception as e:
            if verbose:
                print(f"[WRITE ERROR] {e}")
            return [str(e)]

    os.rename(temp_output, output_path)
    return []

def print_status(index, total, name, status, elapsed=None):
    extra = f" [{elapsed // 60:02.0f}:{elapsed % 60:02.0f}]" if elapsed is not None else ""
    print(f"Processed {index+1}/{total} - [{name}] - Status: {status}{extra}")

def process_folder(index, folder, total, output_dir, delete_cng, ocr, verbose):
    start = time.time()
    name = os.path.basename(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print_status(index, total, name, SYMBOLS['skip'])
        return
    output_file = os.path.join(output_dir, f"NGM_{yyyymm}.pdf")
    if os.path.exists(output_file):
        print_status(index, total, name, SYMBOLS['exist'])
        return
    if os.path.exists(output_file + ".chk"):
        os.remove(output_file + ".chk")

    images = get_image_files(folder, delete_cng=delete_cng)
    if not images:
        print_status(index, total, name, SYMBOLS['skip'])
        return

    failed = build_pdf(images, output_file, ocr=ocr, verbose=verbose)
    symbol = SYMBOLS['fail' if failed else 'done'] + (SYMBOLS['ocr'] if ocr and not failed else '')
    print_status(index, total, name, symbol, elapsed=int(time.time() - start))

def run_batch(root, output_dir, jobs, delete_cng, ocr, verbose):
    print("Legend: ✅ Success   🟦 Existing   ⏭️ Skipped   ❌ Failed   🔤 OCR\n")
    print(f"Scanning directory tree under '{root}'... please wait")
    t0 = time.time()
    folders = fast_find_dirs(root)
    print(f"Found {len(folders)} folders in {time.time() - t0:.2f} seconds.\n")

    os.makedirs(output_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for i, folder in enumerate(folders):
            executor.submit(process_folder, i, folder, len(folders), output_dir, delete_cng, ocr, verbose)

def get_target_folder(rootdir, yyyymm, verbose=False):
    print(f"Looking for issue {yyyymm} in {rootdir}...")
    t0 = time.time()
    matches = []
    for path in Path(rootdir).rglob(f'{yyyymm}*'):
        if path.is_dir():
            matches.append(str(path))
    if not matches:
        print("No matching folders found.")
        sys.exit(1)
    elif len(matches) == 1:
        print(f"Found: {os.path.basename(matches[0])} [{int(time.time() - t0)} sec]")
        return matches[0]
    else:
        for i, path in enumerate(matches):
            print(f"{i+1}: {path}")
        choice = int(input("Select one: "))
        print(f"Found: {os.path.basename(matches[choice - 1])} [{int(time.time() - t0)} sec]")
        return matches[choice - 1]

def main():
    parser = argparse.ArgumentParser(
        description="Bind National Geographic JPG/CNG scans into a single PDF file.",
        epilog="""
Examples:
  Bind all issues recursively (multi-threaded):
    ngb_binder.py --all /path/to/root --output /path/to/output --jobs 4

  Bind a single issue by date:
    ngb_binder.py /path/to/root 199412 --output /path/to/output

  Bind a specific folder:
    ngb_binder.py --dir /exact/folder/path --output /path/to/output

Notes:
- OCR with --ocr embeds searchable text in the PDF
- --remove will delete successfully converted .cng files
- This script is ideal for prepping files before importing to Paperless-ngx or similar
"""
    )
    parser.add_argument('--all', action='store_true', help='Recursively convert all folders under root')
    parser.add_argument('--dir', help='Use exact directory (skip scanning)')
    parser.add_argument('--output', default=os.getcwd(), help='Directory to write PDFs')
    parser.add_argument('--jobs', type=int, default=2, help='Parallel jobs for batch mode')
    parser.add_argument('--ocr', action='store_true', help='Enable OCR text layer using Tesseract')
    parser.add_argument('--remove', '-r', action='store_true', help='Delete CNGs after successful conversion')
    parser.add_argument('--verbose', action='store_true', help='Print verbose debugging information')
    parser.add_argument('src', nargs='?', help='Root folder or input folder')
    parser.add_argument('yyyymm', nargs='?', help='6-digit issue date (YYYYMM)')
    args = parser.parse_args()

    if args.all:
        if not args.src:
            print("Error: You must specify a root folder with --all")
            sys.exit(1)
        run_batch(args.src, args.output, args.jobs, args.remove, args.ocr, args.verbose)
    elif args.dir:
        folder = args.dir
        yyyymm = extract_yyyymm(folder)
        if not yyyymm:
            print(f"Invalid directory: {folder}")
            sys.exit(1)
        process_folder(0, folder, 1, args.output, args.remove, args.ocr, args.verbose)
    elif args.src and args.yyyymm:
        folder = get_target_folder(args.src, args.yyyymm, args.verbose)
        process_folder(0, folder, 1, args.output, args.remove, args.ocr, args.verbose)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

