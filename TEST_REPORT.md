# Initial indexing and search validation

Tested against the 13 PDF files included in `documents/`.

- PDF documents detected: 13
- Total PDF pages: 871
- Pages with extractable text indexed: 831
- Pages with no extractable text: 40
- SQLite FTS5 query checks: `tender` returned 463 matching pages; `EMD` returned 52; `eligibility` returned 5.
- Sample query timings in the build environment were approximately 0.97 ms for `tender`, 0.02 ms for `EMD`, and 0.01 ms for `eligibility`. These are one-time sample measurements on this environment, not a production SLA; actual timings vary with hardware and query.

## Follow-up needed

The 40 pages without extractable text may be blank pages, scanned/image-only pages, or PDFs with unusual text encoding. Audit them before production. If any contain visible text, add OCR to the ingestion pipeline and re-index those pages. Page-level search results use the PDF's 1-based page number.
