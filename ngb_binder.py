#!/usr/bin/env python3
import os
import re
import sys
import time
import argparse
import tempfile
import uuid
import shutil
from pathlib import Path
from PIL import Image
from pytesseract import image_to_pdf_or_hocr
import pikepdf
from concurrent.futures import ThreadPoolExecutor

SYMBOLS = {
    'skip': '⏭️',
    'done': '✅',
    'fail': '❌',
    'exist': '🟦',
    'ocr': '🔤'
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
    return match.group(1) if match else None

def add_file(p, is_main, main_pages, extras, seen):
    if is_main:
        main_pages.append(p)
    else:
        extras.append(p)
    seen.add(p.stem.lower())

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
        if ext == '.jpg':
            add_file(entry, name.lower().startswith('ngm_'), main_pages, extras, seen)
        elif ext == '.cng':
            converted = convert_cng_to_jpg(entry, delete=delete_cng)
            if converted and converted.stem.lower() not in seen:
                add_file(converted, converted.name.lower().startswith('ngm_'), main_pages, extras, seen)

    return sorted(main_pages) + sorted(extras)

def pdf_has_ocr(pdf_path):
    try:
        with pikepdf.open(pdf_path) as pdf:
            for page in pdf.pages:
                if '/Font' in page.get('/Resources', {}):
                    return True
    except Exception:
        pass
    return False

def build_pdf(images, output_path, ocr=False, fail_log=None, verbose=False):
    temp_output = output_path + ".chk"
    if not images:
        return ['NO_IMAGES']

    if not ocr:
        image_objs = []
        for f in images:
            try:
                with Image.open(f) as im:
                    image_objs.append(im.convert("RGB"))
            except Exception as e:
                if verbose:
                    print(f"[ERROR] Failed to load image {f}: {e}")
        if image_objs:
            try:
                image_objs[0].save(temp_output, save_all=True, append_images=image_objs[1:], format='PDF')
                os.rename(temp_output, output_path)
                return []
            except Exception as e:
                if verbose:
                    print(f"[ERROR] Failed to write PDF: {e}")
                return ['WRITE_ERROR']
        return ['IMAGE_OPEN_FAIL']

    # OCR path
    ocr_tempdir = os.path.join(os.path.dirname(output_path), f"ocr_{uuid.uuid4().hex[:8]}")
    os.makedirs(ocr_tempdir, exist_ok=True)
    failed_ocr = 0

    for i, img_path in enumerate(images):
        try:
            pdf_bytes = image_to_pdf_or_hocr(str(img_path), extension='pdf')
            with open(os.path.join(ocr_tempdir, f"{i:03}.pdf"), 'wb') as f:
                f.write(pdf_bytes)
        except Exception as e:
            print(f"[WARNING] [OCR FAIL] {img_path.name}: {e}")
            failed_ocr += 1

    if verbose:
        print(f"[INFO] OCR completed for {len(images) - failed_ocr}/{len(images)} pages.")
        if failed_ocr:
            print(f"[INFO] Failed OCR pages were skipped but included in the PDF as-is.")

    try:
        merger = pikepdf.Pdf.new()
        for fpath in sorted(Path(ocr_tempdir).glob("*.pdf")):
            merger.pages.extend(pikepdf.open(fpath).pages)
        merger.save(temp_output)
        merger.close()
        os.rename(temp_output, output_path)
    except Exception as e:
        print(f"[ERROR] Merging OCR PDFs failed: {e}")
        return ['MERGE_FAIL']

    shutil.rmtree(ocr_tempdir)
    return [] if failed_ocr < len(images) else ['ALL_OCR_FAILED']

def print_status(index, total, name, symbol, duration=None):
    time_str = f" [{int(duration // 60):02}:{int(duration % 60):02}]" if duration else ""
    print(f"Processed {index + 1}/{total} - [{name}] - Status: {symbol}{time_str}")

def process_folder(index, folder, total, output_dir, delete_cng, ocr, verbose):
    start_time = time.time()
    name = os.path.basename(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print_status(index, total, name, SYMBOLS['skip'])
        return

    output_file = os.path.join(output_dir, f'NGM_{yyyymm}.pdf')
    if os.path.exists(output_file):
        if ocr and not pdf_has_ocr(output_file):
            if verbose:
                print(f"[INFO] Existing PDF found but missing OCR: {output_file}")
        else:
            print_status(index, total, name, SYMBOLS['exist'])
            return

    if os.path.exists(output_file + ".chk"):
        os.remove(output_file + ".chk")

    images = get_image_files(folder, delete_cng=delete_cng)
    if not images:
        print_status(index, total, name, SYMBOLS['skip'])
        return

    failed = build_pdf(images, output_file, ocr=ocr, fail_log=None, verbose=verbose)
    duration = time.time() - start_time
    symbol = SYMBOLS['fail'] if failed else SYMBOLS['done'] + (SYMBOLS['ocr'] if ocr else '')
    print_status(index, total, name, symbol, duration)

def run_batch(root, output_dir, jobs, delete_cng, ocr, verbose):
    print("Legend: ✅ = Converted | 🔤 = OCR | 🟦 = Already exists | ⏭️ = Skipped | ❌ = Failed\n")
    print(f"Scanning directory tree under '{root}'... please wait")
    t0 = time.time()
    folders = fast_find_dirs(root)
    print(f"Found {len(folders)} folders in {time.time() - t0:.2f} seconds.\n")

    os.makedirs(output_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for i, folder in enumerate(folders):
            executor.submit(process_folder, i, folder, len(folders), output_dir, delete_cng, ocr, verbose)

def get_target_folder(rootdir, yyyymm):
    print(f"Looking for issue {yyyymm} in {rootdir}...")
    t0 = time.time()
    candidates = []
    for path in Path(rootdir).rglob(f'{yyyymm}*'):
        if path.is_dir():
            candidates.append(str(path))
    if not candidates:
        print("No matching folders found.")
        sys.exit(1)
    elif len(candidates) == 1:
        print(f"Found: {os.path.basename(candidates[0])} [{int(time.time() - t0)} sec]")
        return candidates[0]
    else:
        for i, path in enumerate(candidates):
            print(f"{i+1}: {path}")
        choice = int(input("Select one: "))
        print(f"Found: {os.path.basename(candidates[choice - 1])} [{int(time.time() - t0)} sec]")
        return candidates[choice - 1]

def main():
    parser = argparse.ArgumentParser(
        description="Bind National Geographic scans (JPG or CNG) into a PDF. Optionally apply OCR.",
        epilog="""
Examples:
  ngb_binder.py --all /path/to/all/issues --output /path/to/output
  ngb_binder.py /path/to/all/issues 199412 --output /out --ocr
  ngb_binder.py --dir /exact/path/to/folder --ocr --remove
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--all', action='store_true', help='Process all folders under source path')
    parser.add_argument('--dir', metavar='DIR', help='Bind images in this specific directory')
    parser.add_argument('--output', default=os.getcwd(), help='Output directory (default: current)')
    parser.add_argument('--jobs', type=int, default=2, help='Parallel workers (default: 2)')
    parser.add_argument('--ocr', action='store_true', help='Enable OCR for text-searchable PDF')
    parser.add_argument('--remove', '-r', action='store_true', help='Delete CNGs after successful JPG conversion')
    parser.add_argument('--verbose', action='store_true', help='Print debug and info messages')
    parser.add_argument('src', nargs='?', help='Source folder root')
    parser.add_argument('yyyymm', nargs='?', help='Target issue date (e.g. 199412)')
    args = parser.parse_args()

    if args.all:
        run_batch(args.src, args.output, args.jobs, args.remove, args.ocr, args.verbose)
    elif args.dir:
        folder = args.dir
        yyyymm = extract_yyyymm(folder)
        if not yyyymm:
            print(f"Invalid directory format: {folder}")
            sys.exit(1)
        process_folder(0, folder, 1, args.output, args.remove, args.ocr, args.verbose)
    elif args.src and args.yyyymm:
        folder = get_target_folder(args.src, args.yyyymm)
        process_folder(0, folder, 1, args.output, args.remove, args.ocr, args.verbose)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

