# National Geographic Binder (`ngb_binder.py`)

This script converts scanned National Geographic magazine images into searchable PDF files, supporting `.jpg` and proprietary `.cng` formats. It includes optional OCR support and various modes for processing specific folders, dates, or entire archives.

---

## 🔰 Symbol Legend (used in status output)

- ✅ = Successfully converted
- ✅🔤 = Successfully converted **with OCR**
- 🟦 = PDF already exists, skipping
- ⏭️ = Skipped (invalid folder or no relevant image files)
- ❌ = Failed during processing

---

## 🔧 Supported Modes

### 1. Bind a single issue by date

```bash
./ngb_binder.py /path/to/archive 199412
```

Searches for a folder matching the date prefix (e.g. `199412*`) and binds its images into `NGM_199412.pdf`.

---

### 2. Bind all `.jpg` and `.cng` images in a specific folder (no date guessing)

```bash
./ngb_binder.py --dir /exact/folder/path
```

Useful for edge cases where the folder name doesn’t follow standard naming but contains valid image data.

---

### 3. Batch mode: scan entire archive and convert all issues in parallel

```bash
./ngb_binder.py --all /path/to/archive --output /path/to/pdf_output --jobs 4
```

Recursively scans for issue folders under the specified root and processes all of them.

---

## 🧠 Optional Features

### OCR support (searchable PDFs)

```bash
./ngb_binder.py ... --ocr
```

Applies Tesseract OCR to each page before PDF generation. Useful for enabling text search and integration with systems like [Paperless NGX](https://github.com/paperless-ngx/paperless-ngx) without further OCR processing.

> Note: This feature significantly increases CPU usage and memory. It's designed to run on powerful machines, not Raspberry Pi or limited environments.

---

### Remove original `.cng` files after successful conversion

```bash
./ngb_binder.py ... --remove
```

Deletes `.cng` files **only after** they are successfully converted to `.jpg`. Reduces storage usage.

---

### Verbose logging to stdout

```bash
./ngb_binder.py ... --verbose
```

Prints debug messages and failure reasons directly to the terminal (instead of relying on `failed.log` which may trigger I/O errors).

---

## 🔡 Example Usage

- Convert all issues with OCR and delete CNGs after processing:

```bash
./ngb_binder.py --all /mnt/data/NGM_Archive --output /mnt/data/NGM_PDFs --ocr --remove --jobs 4
```

- Convert one specific issue:

```bash
./ngb_binder.py /mnt/data/NGM_Archive 199805 --output /mnt/data/NGM_PDFs
```

- Convert one non-standard folder:

```bash
./ngb_binder.py --dir /mnt/data/NGM_Archive/CNG_MISC_DISC3/1998_extras
```

---

## 📦 Python Dependencies

Make sure the following Python packages are installed:

- `Pillow`
- `PyPDF2`
- `pytesseract`
- `pikepdf`

Install them using pip:

```bash
pip install Pillow PyPDF2 pytesseract pikepdf
```

Also ensure [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) is installed and available in your system path.

---

## 🗃 Notes

- If your input files are in `.iso`, `.tar`, or `.tgz` formats, extract them first.
- `.cng` is a proprietary format used in the original National Geographic collection. The script automatically decodes and converts them.
- Temporary folders are created in the output directory for OCR processing and removed afterward.

