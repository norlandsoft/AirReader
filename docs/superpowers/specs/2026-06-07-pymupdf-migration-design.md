# PyMuPDF Migration Design

> Replace OpenDataLoader (Java) with PyMuPDF + pdfplumber (Python) for PDF text and image extraction.

## Background

The current AirReader service is a Spring Boot (Java 21) application that uses:
- `opendataloader-pdf-core:1.3.0` for PDF-to-Markdown conversion
- Apache PDFBox 3.0.4 (transitive dep) for original-resolution image extraction
- A complex 200+ line aspect-ratio matching algorithm to replace ODL's low-res images with PDFBox originals

Pain points:
- ODL generates low-resolution images (~40% of original), requiring a fragile matching+replacement pipeline
- The Java/PDFBox image extraction requires parsing content streams, y-coordinate filtering, and multi-criteria matching
- The chunked processing (5-page splits) adds significant complexity

## Decision

Migrate entirely to Python (FastAPI + PyMuPDF + pdfplumber), keeping the existing API contract.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web framework | FastAPI + uvicorn | REST API, async, auto OpenAPI docs |
| PDF extraction | PyMuPDF (fitz) | Text + original-resolution images |
| Table extraction | pdfplumber | Markdown tables from PDF tables |
| File upload | python-multipart | multipart/form-data handling |

## Project Structure

```
/opt/AirReader/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry + startup config
│   ├── router/
│   │   ├── __init__.py
│   │   └── convert.py       # /api/v1/convert/file, /api/v1/health
│   ├── service/
│   │   ├── __init__.py
│   │   └── pdf_extractor.py # Core extraction (PyMuPDF + pdfplumber)
│   └── model/
│       ├── __init__.py
│       └── schemas.py       # Request/response models
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── skills/                   # Unchanged
```

## Core Extraction Logic (pdf_extractor.py)

### Flow

```
PDF input
  ├── 1. PyMuPDF: extract text per page (page.get_text("text"))
  ├── 2. PyMuPDF: extract images at original resolution
  │     page.get_images() → doc.extract_image(xref) → raw bytes
  ├── 3. pdfplumber: extract tables
  │     page.extract_tables() → Markdown table syntax
  │     Insert tables at correct y-position within page text
  └── 4. Assemble Markdown: text + tables + image references
```

### Text Extraction

- Primary: `page.get_text("text")` for clean text per page
- pdfplumber `page.extract_text()` as fallback for better layout when needed
- Pages separated by `---` horizontal rules

### Image Extraction (simplified from 200+ lines to ~30 lines)

1. `page.get_images(full=True)` — get all image references per page
2. `doc.extract_image(xref)` — extract raw bytes + original format (PNG/JPEG/JP2)
3. Write to `{baseName}_images/` directory
4. Insert `![]({baseName}_images/img_p{page}_{index}.{ext})` in Markdown

No aspect-ratio matching needed — PyMuPDF extracts the original embedded image directly.

### Table Extraction

- `page.extract_tables()` returns 2D arrays
- Convert to Markdown table syntax (`| col1 | col2 |`)
- Use `page.find_tables()` for y-coordinate positioning within page text flow

### Header/Footer Filtering

- Same thresholds as Java version: skip images with y > 85% or y < 10% of page height
- Use pdfplumber's element coordinates for positioning

### Large File Handling

- PyMuPDF processes pages individually — no need for chunk splitting
- Memory: only current page's image data in memory at a time
- Eliminates the 5-page chunk complexity entirely

## API Contract (Fully Compatible)

### Endpoints

```
GET  /api/v1/health         → {"status": "healthy", "version": "3.0.0"}
POST /api/v1/convert/file   → application/zip (streaming)
```

### Zip Structure (unchanged)

```
zip
├── meta.json
├── {baseName}.md
└── {baseName}_images/
    ├── img_p0_0.png
    └── ...
```

### meta.json (success)

```json
{
    "filename": "test.pdf",
    "file_size_bytes": 1234567,
    "processing_time": 1.23,
    "status": "success"
}
```

### meta.json (failure)

```json
{
    "filename": "test.pdf",
    "file_size_bytes": 1234567,
    "processing_time": 0.5,
    "status": "failure",
    "errors": [{"code": "EXTRACTION_FAILED", "message": "..."}]
}
```

### Error Handling

- Validation failures and extraction failures both return zip with status=failure
- HTTP status code always 200 (matches Java behavior)
- Temp directories cleaned in `finally` blocks

## Docker Configuration

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### requirements.txt

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
PyMuPDF>=1.24.0
pdfplumber>=0.11.0
```

### docker-compose.yml

- Remove Maven build stage
- Use Python image directly
- Keep port 8000 mapping

## Cleanup

- Delete: `pom.xml`, `src/` directory, `scripts/build.sh`, `target/`
- Update: `README.md`, `.dockerignore`, `.gitignore`
- Version bump to `3.0.0` (major architecture change)

## Migration Summary

| Aspect | Before (Java) | After (Python) |
|--------|--------------|----------------|
| Language | Java 21 | Python 3.11 |
| Framework | Spring Boot 3.3.5 | FastAPI |
| PDF library | OpenDataLoader + PDFBox | PyMuPDF + pdfplumber |
| Image extraction | Aspect-ratio matching (~200 lines) | Direct extraction (~30 lines) |
| Chunked processing | 5-page splits with merge | Per-page processing (native) |
| Total core code | ~560 lines | ~200 lines (est.) |
| License | ODL license + Apache 2.0 | AGPL (PyMuPDF) |

## Open Questions

None — all design decisions confirmed by user.
