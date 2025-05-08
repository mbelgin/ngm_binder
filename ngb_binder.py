#!/usr/bin/env python3
import os
import re
import sys
import argparse
import shutil
import time
import tempfile
import uuid
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import pytesseract
import pikepdf

SYMBOLS = {
    'skip': '⏭️',
    'done': '✅',
    'ocr': '🔤',
    'fail': '❌',
    'exist': '🟦'
}

def log(msg, verbose):
    if verbose:
        print(msg)

def fast_find_dirs(root):
    result = []
    for dirpath, dirnames, _ in os.walk(root):
        result.append(dirpath)
    return result

def extract_yyyymm(foldername):
    match = re.search(r'(\d{6})', os.path.basename(foldername))
    return match.group(1) if match else None

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
            (main_pages if is_main else extras).append(p)
            seen.add(p.stem.lower())

        if ext == '.jpg':
            add_file(entry, name.lower().startswith('ngm_'))
        elif ext == '.cng':
            converted = convert_cng_to_jpg(entry, delete=delete_cng)
            if converted and converted.stem.lower() not in seen:
                add_file(converted, converted.name.lower().startswith('ngm_'))

    return sorted(main_pages) + sorted(extras)

def ocr_images_to_pdfs(images, temp_dir, verbose):
    ocr_pdfs = []
    for i, img_path in enumerate(images):
        dest = os.path.join(temp_dir, f"{i:03d}.pdf")
        try:
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(str(img_path), extension='pdf')
            with open(dest, 'wb') as f:
                f.write(pdf_bytes)
            ocr_pdfs.append(dest)
        except Exception as e:
            log(f"[OCR FAIL] {img_path}: {e}", verbose)
            return None
    return ocr_pdfs

def merge_with_pikepdf(pdf_paths, output_path):
    try:
        with pikepdf.Pdf.new() as merged:
            for pdf in pdf_paths:
                src = pikepdf.Pdf.open(pdf)
                merged.pages.extend(src.pages)
            merged.save(output_path)
        return True
    except Exception:
        return False

def build_pdf(images, output_path, ocr=False, verbose=False):
    temp_output = output_path + ".chk"
    os.makedirs(os.path.dirname(temp_output), exist_ok=True)

    if not ocr:
        image_objs = []
        for f in images:
            try:
                with Image.open(f) as im:
                    image_objs.append(im.convert("RGB"))
            except Exception as e:
                log(f"[IMG FAIL] {f}: {e}", verbose)
                return False
        try:
            image_objs[0].save(temp_output, save_all=True, append_images=image_objs[1:], format='PDF')
            os.rename(temp_output, output_path)
            return True
        except Exception as e:
            log(f"[PDF WRITE FAIL] {e}", verbose)
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return False
    else:
        temp_dir = os.path.join(os.path.dirname(output_path), f"ocr_{uuid.uuid4().hex[:8]}")
        os.makedirs(temp_dir, exist_ok=True)
        ocr_pdfs = ocr_images_to_pdfs(images, temp_dir, verbose)
        if not ocr_pdfs:
            return False
        result = merge_with_pikepdf(ocr_pdfs, temp_output)
        if result:
            os.rename(temp_output, output_path)
            shutil.rmtree(temp_dir)
            return True
        else:
            log(f"[MERGE FAIL] Could not merge OCR PDFs", verbose)
            return False

def print_status(index, total, name, status, elapsed=None):
    suffix = f" [{elapsed // 60}:{elapsed % 60:02}]" if elapsed else ""
    print(f"Processed {index + 1}/{total} - [{name}] - Status: {status}{suffix}")

def process_folder(index, folder, total, output_dir, delete_cng, ocr, verbose):
    start = time.time()
    name = os.path.basename(folder)
    yyyymm = extract_yyyymm(folder)
    if not yyyymm:
        print_status(index, total, name, SYMBOLS['skip'])
        return
    output_file = os.path.join(output_dir, f'NGM_{yyyymm}.pdf')
    if os.path.exists(output_file):
        print_status(index, total, name, SYMBOLS['exist'])
        return
    if os.path.exists(output_file + ".chk"):
        os.remove(output_file + ".chk")

    images = get_image_files(folder, delete_cng=delete_cng)
    if not images:
        print_status(index, total, name, SYMBOLS['skip'])
        return

    success = build_pdf(images, output_file, ocr=ocr, verbose=verbose)
    elapsed = int(time.time() - start)
    symbol = SYMBOLS['done'] + SYMBOLS['ocr'] if (success and ocr) else SYMBOLS['done'] if success else SYMBOLS['fail']
    print_status(index, total, name, symbol, elapsed)

def run_batch(root, output_dir, jobs, delete_cng, ocr, verbose):
    print(f"Scanning directory tree under '{root}'... please wait")
    t0 = time.time()
    folders = fast_find_dirs(root)
    print(f"Found {len(folders)} folders in {time.time() - t0:.2f} seconds.\n")

    os.makedirs(output_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for i, folder in enumerate(folders):
            executor.submit(process_folder, i, folder, len(folders), output_dir, delete_cng, ocr, verbose)

def get_target_folder(rootdir, yyyymm, verbose):
    t0 = time.time()
    print(f"Looking for issue {yyyymm} in {rootdir}...")
    candidates = []
    for path in Path(rootdir).rglob(f'{yyyymm}*'):
        if path.is_dir():
            candidates.append(str(path))
    if not candidates:
        print("No matching folders found.")
        sys.exit(1)
    print(f"Found: {os.path.basename(candidates[0])} [{int(time.time()-t0)} sec]")
    return candidates[0]

def main():
    parser = argparse.ArgumentParser(description="Bind National Geographic JPG/CNG scans into PDF files.")
    parser.add_argument('--all', action='store_true', help='Convert all issues under the root directory')
    parser.add_argument('--output', default=os.getcwd(), help='Output directory for final PDFs')
    parser.add_argument('--jobs', type=int, default=2, help='Number of parallel workers (default: 2)')
    parser.add_argument('--remove', '-r', action='store_true', help='Remove successfully converted CNG files')
    parser.add_argument('--ocr', action='store_true', help='Use Tesseract to add OCR to the PDF')
    parser.add_argument('--verbose', action='store_true', help='Enable debug/status logging to stdout')
    parser.add_argument('src', nargs='?', help='Root folder or exact folder path')
    parser.add_argument('yyyymm', nargs='?', help='Date in YYYYMM format (only needed if not using --all)')
    args = parser.parse_args()

    if args.all:
        run_batch(args.src, args.output, args.jobs, args.remove, args.ocr, args.verbose)
    elif args.src and args.yyyymm:
        folder = get_target_folder(args.src, args.yyyymm, args.verbose)
        process_folder(0, folder, 1, args.output, args.remove, args.ocr, args.verbose)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

