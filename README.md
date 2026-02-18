# AutoFiler

Automated file monitor and organizer for Windows. AutoFiler watches an intake folder for new files, classifies them by document content type using OCR-based text extraction and keyword/pattern matching, and routes them to organized destination folders — or queues them for manual review when confidence is low.

## How It Works

```
[Intake Folder] --> [Folder Watcher] --> [Format Detection]
                                                |
                                      [Text Extraction (OCR)]
                                                |
                                    [Content Classification]
                                      (keywords + patterns)
                                                |
                                        [Confidence Scoring]
                                            |          |
                                    >= threshold    < threshold
                                            |          |
                                      [Auto-File]   [Review Queue]
                                            |          |
                                    [Rename & Move]  [User Prompts]
                                            |          |
                                  [Destination]    [Type Creation]
```

Files are classified by **document content** — not just file format. The same PDF can be identified as a bank statement, W-2, invoice, or any other type based on the text found inside it. New document types can be created on the fly during manual review, making the system self-expanding.

## Features

- **Continuous Monitoring** — Watches an intake folder for new files using watchdog
- **OCR Text Extraction** — Extracts text from PDFs (via Tesseract + Poppler), DOCX files, and images
- **Content Classification** — Matches extracted text against keyword and regex pattern definitions
- **Confidence Scoring** — Weighted scoring across format, keyword, pattern, and reference signals
- **Auto-Filing** — High-confidence files are renamed and moved to type-specific destination folders
- **Review Queue** — Low-confidence files are queued for interactive manual classification
- **Dynamic Type Creation** — Define new document types during review; immediately available for future classification
- **Edge Case Handling** — Guards against zero-byte files, locked files, temp files, password-protected PDFs
- **Structured Logging** — JSON-line log of all filing, review, and error events
- **Desktop GUI** — Tkinter-based Start/Stop launcher with live activity log

## Requirements

- Python 3.10+
- [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- [Poppler](https://github.com/osber/poppler-windows/releases) (for PDF-to-image conversion)

## Installation

1. Clone the repository and create a virtual environment:
   ```
   git clone https://github.com/krusew123/AutoFiler.git
   cd AutoFiler
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install Python dependencies:
   ```
   pip install watchdog python-magic-bin pytesseract pdf2image Pillow python-docx
   ```

3. Install Tesseract-OCR and Poppler, then update paths in `Config/settings.json`.

4. Create the data directories referenced in `Config/settings.json` (intake, filed, review, logs).

## Usage

### GUI Launcher
```
python autofiler_gui.py
```
Or double-click the desktop shortcut if configured.

### Console Watcher
```
python autofiler.py
```
Press `Ctrl+C` to stop.

### Manual Review
```
python review.py
```
Walks through queued files one at a time for classification.

## Project Structure

```
AutoFiler/
├── autofiler.py              -- Console watcher entry point
├── autofiler_gui.py          -- Desktop GUI launcher
├── review.py                 -- Manual review CLI entry point
├── src/
│   ├── config_loader.py      -- Load & cache JSON config files
│   ├── detectors.py          -- Format detection (extension, MIME, metadata)
│   ├── content_extractor.py  -- OCR + text parsing (PDF, DOCX, images)
│   ├── content_matcher.py    -- Keyword and regex pattern matching
│   ├── classifier.py         -- Orchestrate format + content classification
│   ├── scorer.py             -- Weighted confidence scoring
│   ├── router.py             -- Threshold routing (auto-file / review)
│   ├── name_generator.py     -- Resolve naming patterns into filenames
│   ├── filer.py              -- Move & rename to destination folder
│   ├── pipeline.py           -- Full pipeline: classify > score > route > file
│   ├── guards.py             -- Pre-processing edge case checks
│   ├── logger.py             -- Structured JSON-line logging
│   ├── review_queue.py       -- Review folder scan & state tracking
│   ├── review_prompt.py      -- Interactive terminal prompts
│   ├── review_session.py     -- Review session runner
│   └── type_creator.py       -- New type definition & persistence
├── Config/
│   ├── settings.json         -- Runtime parameters (paths, threshold, polling)
│   ├── type_definitions.json -- Document type registry (grows during review)
│   └── References/
│       ├── classification_rules.json  -- Signal weights
│       ├── folder_mappings.json       -- Type to destination mapping
│       └── naming_conventions.json    -- Type to naming pattern mapping
```

## Configuration

All configuration lives in `Config/settings.json`:

| Setting | Description |
|---|---|
| `intake_path` | Folder the watcher monitors for new files |
| `destination_root` | Root directory for classified file output |
| `review_path` | Staging folder for low-confidence files |
| `confidence_threshold` | Score cutoff (0.0-1.0) for auto-filing vs review |
| `polling_interval` | Seconds between watcher poll cycles |
| `tesseract_path` | Path to Tesseract-OCR executable |
| `poppler_path` | Path to Poppler bin directory |

## Adding Document Types

Document types can be added in two ways:

1. **During review** — When classifying a file manually, select "Create a new type" and fill in the prompted fields.
2. **Editing config** — Add entries to `type_definitions.json`, `folder_mappings.json`, and `naming_conventions.json`.

Each type definition includes:
- `container_formats` — Expected file extensions (e.g., `.pdf`)
- `content_keywords` — Terms to match in OCR-extracted text
- `content_patterns` — Regex patterns for structural detection
- `keyword_threshold` — Minimum keyword matches required
- `destination_subfolder` — Where to file matched documents
- `naming_pattern` — Filename template (e.g., `{original_name}_{date}`)
