# National Geographic Binder (`new_ngb_binder.py`)

This script is designed to recursively process folders containing scanned images from the *Complete National Geographic* collection and bind them into PDF files. It handles `.jpg` and `.cng` image formats and includes options for batch processing, specific issue conversion, and direct folder-based PDF generation.

---

## Features

- Recursively scans folders for images organized by issue (e.g., `YYYYMM01`)
- Converts `.cng` (National Geographic proprietary format) to `.jpg` using XOR 239
- Optionally deletes `.cng` files after successful conversion with `--delete` or `-r`
- Skips folders without valid images or if PDF already exists
- Checkpointing via `.pdf.chk` files to avoid incomplete outputs
- Outputs status lines per folder with intuitive symbols:
  - ✅ Converted
  - 🟦 Existing (PDF already present)
  - ⏭️ Skipped (invalid folder, subfolder, or no images)
  - ❌ Failed (conversion errors)

---

## Requirements

- Python 3.7+
- `Pillow` (Python Imaging Library)

---

## Usage

```bash
python3 new_ngb_binder.py [OPTIONS]
```

### Batch process all folders (multi-threaded)
```bash
python3 new_ngb_binder.py --all ROOTDIR --output OUTPUTDIR --jobs 12
```

### Convert only a specific folder (exact path)
```bash
python3 new_ngb_binder.py --dir FOLDER_PATH --output OUTPUTDIR
```

### Convert issue by date (e.g., 200312 for Dec 2003)
```bash
python3 new_ngb_binder.py ROOTDIR 200312 --output OUTPUTDIR
```

---

## Options

- `--all`  
  Process all folders recursively from the given root directory

- `--output OUTPUTDIR`  
  Directory to save the resulting PDF files (default: current working directory)

- `--jobs JOBS`  
  Number of parallel threads to use during batch processing (default: 4)

- `--dir DIR`  
  Exact path to a folder to bind into a PDF without guessing format

- `--delete`, `-r`  
  Remove `.cng` files after successful conversion to `.jpg`

- `src`  
  Root directory to search for folders if not using `--dir` or `--all`

- `yyyymm`  
  Issue date (e.g., `199911`) to match folders containing scans for that issue

---

## Notes

- If your scans are packaged in `.iso`, `.tar`, or `.tgz` formats, **extract them first** before using this script.
- The script uses simple lexicographic ordering to determine image sequence.
- Extras (files not starting with `NGM_`) are appended at the end of the PDF.
- Incomplete PDFs are stored as `.pdf.chk` and renamed only upon successful completion.

---

## Example

```bash
python3 new_ngb_binder.py --all "The Complete National Geographic 1888-2010-JPGs" --output ./NGM_PDFs --jobs 8
```


