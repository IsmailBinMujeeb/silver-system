# Tender Document Search

A local web application that searches tender PDF text and reports the matching PDF filename, page number, and a text snippet. The included sample `documents/` folder contains 13 tender PDFs from the supplied ZIP.

## Features
- Page-level indexing, so matches return the PDF page number.
- SQLite FTS5 full-text index for fast repeated searches.
- Exact phrase mode and all-words mode.
- Result snippets with highlighted matches.
- Upload additional PDFs; new PDFs are indexed on upload.
- Re-index action skips unchanged PDFs based on file size and modification time.
- Search timing and index statistics.
- No cloud API or paid service required.

## Run on Windows (easy way)
1. Install Python 3.11 or newer from https://www.python.org/downloads/ (enable **Add Python to PATH**).
2. Extract this project ZIP to a normal folder, e.g. `D:\TenderDocumentSearch`.
3. Double-click `run_windows.bat`. The first run creates a virtual environment and installs packages.
4. Wait for the first indexing pass to finish.
5. Open `http://127.0.0.1:5000` in your browser.

## Run in VS Code / PowerShell
Open the project folder in VS Code, then run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, use `run_windows.bat`, or run `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and then `\.venv\Scripts\python.exe app.py` without activating.

## How it works
- On startup, the app checks PDFs in `documents/` and indexes new/changed files.
- Text is extracted one page at a time with PyMuPDF.
- Each text-bearing page is saved in the SQLite FTS5 index in `data/tender_search.db` with its filename and 1-based page number.
- Search queries hit the index rather than opening every PDF again.
- Search results are one row per matching page. A page containing multiple occurrences appears once in results.

## Important limitation: scanned PDFs
Text-based PDFs are searchable immediately. A scanned PDF with image-only pages may return no text for those pages. Those pages need OCR (for example, Tesseract) before they can be indexed. The app reports page counts, but does not silently claim OCR coverage. Before production use, audit documents with many empty text pages and add an OCR ingestion step if required.

## Production considerations
This is a local working prototype, not a secured public deployment. Before exposing it to a network, add authentication, upload limits appropriate to your environment, access controls, logging, backups, and background indexing jobs. Benchmark with your expected number of PDFs/pages. For very large corpora or advanced fuzzy/semantic search, evaluate a dedicated search engine; keep page-level metadata in the index regardless.
