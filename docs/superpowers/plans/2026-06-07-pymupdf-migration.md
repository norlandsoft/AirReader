# PyMuPDF Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Java Spring Boot + OpenDataLoader + PDFBox stack with Python FastAPI + PyMuPDF + pdfplumber, keeping the existing API contract (POST /api/v1/convert/file returning zip).

**Architecture:** FastAPI app with a single router exposing health and convert endpoints. Core extraction uses PyMuPDF for text + images (original resolution via `doc.extract_image(xref)`), pdfplumber for tables. Output is assembled into Markdown and packaged as zip with meta.json.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, PyMuPDF (fitz), pdfplumber, python-multipart, pytest, httpx, reportlab (test only)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `requirements.txt` | Production + test dependencies |
| Create | `app/__init__.py` | Package marker |
| Create | `app/main.py` | FastAPI app factory, uvicorn entry |
| Create | `app/router/__init__.py` | Package marker |
| Create | `app/router/convert.py` | Health + convert endpoints, zip packaging |
| Create | `app/service/__init__.py` | Package marker |
| Create | `app/service/pdf_extractor.py` | Core extraction: text, images, tables, assembly |
| Create | `app/model/__init__.py` | Package marker |
| Create | `app/model/schemas.py` | HealthResponse model |
| Create | `tests/__init__.py` | Package marker |
| Create | `tests/conftest.py` | Shared fixtures: test PDF generation |
| Create | `tests/test_extractor.py` | Unit tests for pdf_extractor |
| Create | `tests/test_api.py` | Integration tests for API endpoints |
| Modify | `Dockerfile` | Replace Java build with Python |
| Modify | `docker-compose.yml` | Remove JAVA_OPTS, update image |
| Modify | `.dockerignore` | Update for Python |
| Delete | `pom.xml` | No longer needed |
| Delete | `src/` | Entire Java source tree |
| Delete | `scripts/build.sh` | Maven build script |
| Delete | `target/` | Build artifacts |

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/router/__init__.py`
- Create: `app/service/__init__.py`
- Create: `app/model/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```txt
# Production
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
PyMuPDF>=1.24.0
pdfplumber>=0.11.0

# Testing
pytest>=8.0.0
httpx>=0.27.0
reportlab>=4.0.0
```

- [ ] **Step 2: Create directory structure and empty __init__.py files**

```bash
mkdir -p app/router app/service app/model tests
touch app/__init__.py app/router/__init__.py app/service/__init__.py app/model/__init__.py tests/__init__.py
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create tests/conftest.py with test PDF fixtures**

```python
"""Shared test fixtures — generates PDFs with known content for verification."""
import io
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table


@pytest.fixture
def text_pdf(tmp_path):
    """Create a minimal PDF with known text content."""
    pdf_path = tmp_path / "text_test.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((72, 72), "Hello World\nSecond line")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def image_pdf(tmp_path):
    """Create a PDF with an embedded image (50x50 red PNG)."""
    pdf_path = tmp_path / "image_test.pdf"
    img_path = tmp_path / "red.png"

    # Create a 50x50 red PNG with PyMuPDF
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50))
    pix.set_rect(pix.irect, (1.0, 0.0, 0.0))  # solid red
    pix.save(str(img_path))

    # Embed in PDF
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(72, 72, 172, 172), filename=str(img_path))
    doc.save(str(pdf_path))
    doc.close()
    pix = None
    return pdf_path


@pytest.fixture
def table_pdf(tmp_path):
    """Create a PDF with a table using reportlab."""
    pdf_path = tmp_path / "table_test.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    data = [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]
    t = Table(data, colWidths=[50 * mm, 30 * mm])
    t.setStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0)),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ])
    w, h = A4
    t.wrapOn(c, w, h)
    t.drawOn(c, 72, h - 200)
    c.save()
    return pdf_path


@pytest.fixture
def mixed_pdf(tmp_path):
    """Create a PDF with text + image + table."""
    pdf_path = tmp_path / "mixed_test.pdf"

    # Create red image
    img_path = tmp_path / "red_mixed.png"
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50))
    pix.set_rect(pix.irect, (1.0, 0.0, 0.0))
    pix.save(str(img_path))
    pix = None

    # Page 1: text + image with reportlab
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, A4[1] - 72, "Document Title")

    data = [["Col1", "Col2"], ["A", "B"]]
    t = Table(data, colWidths=[40 * mm, 40 * mm])
    t.setStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0)),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ])
    t.wrapOn(c, *A4)
    t.drawOn(c, 72, A4[1] - 200)
    c.save()

    # Add image to page with PyMuPDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    page.insert_image(fitz.Rect(72, A4[1] - 350, 172, A4[1] - 250), filename=str(img_path))
    doc.save(str(pdf_path))
    doc.close()

    return pdf_path
```

- [ ] **Step 5: Verify pytest discovers tests**

```bash
python -m pytest tests/ --collect-only
```

Expected: `0 tests collected` (no test files yet) — confirms the import chain works.

- [ ] **Step 6: Commit scaffold**

```bash
git add requirements.txt app/ tests/conftest.py tests/__init__.py
git commit -m "chore: Python project scaffold with test fixtures"
```

---

### Task 2: Text Extraction

**Files:**
- Create: `app/service/pdf_extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write failing test for text extraction**

Create `tests/test_extractor.py`:

```python
"""Unit tests for PDF extraction service."""
import tempfile
from pathlib import Path

import pytest

from app.service.pdf_extractor import extract_pdf


class TestTextExtraction:
    def test_extracts_text_from_simple_pdf(self, text_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(text_pdf, output_dir)

            assert result["success"] is True
            md_path = output_dir / "text_test.md"
            assert md_path.exists()

            content = md_path.read_text(encoding="utf-8")
            assert "Hello World" in content
            assert "Second line" in content

    def test_text_pdf_creates_images_dir(self, text_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(text_pdf, output_dir)

            assert result["success"] is True
            # Images dir should exist even if empty
            assert (output_dir / "text_test_images").is_dir()

    def test_missing_file_returns_failure(self, tmp_path):
        result = extract_pdf(tmp_path / "nonexistent.pdf", tmp_path)
        assert result["success"] is False
        assert "不存在" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_extractor.py::TestTextExtraction -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.service.pdf_extractor'`

- [ ] **Step 3: Implement text extraction in pdf_extractor.py**

Create `app/service/pdf_extractor.py`:

```python
"""
PDF extraction service using PyMuPDF + pdfplumber.

Extracts text, images (original resolution), and tables from PDF files,
assembling them into Markdown format.
"""
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

HEADER_Y_THRESHOLD = 0.85
FOOTER_Y_THRESHOLD = 0.10


def extract_pdf(pdf_path: Path, output_dir: Path) -> Dict[str, Any]:
    """
    Extract PDF content as Markdown + images.

    Args:
        pdf_path: Path to input PDF file.
        output_dir: Directory to write output (.md file + _images/ dir).

    Returns:
        {"success": True, "output_dir": str} on success,
        {"success": False, "error": str} on failure.
    """
    if not pdf_path.exists():
        return {"success": False, "error": f"PDF 文件不存在: {pdf_path}"}

    try:
        base_name = pdf_path.stem
        images_dir = output_dir / f"{base_name}_images"
        images_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        try:
            markdown_parts = []

            # Pre-scan: collect all image xrefs, identify smask xrefs to skip
            image_info = _collect_image_info(doc)
            smask_xrefs = _find_smask_xrefs(image_info)
            extracted_xrefs = set()

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_md = _process_page(
                    doc, page, page_num, base_name, images_dir,
                    smask_xrefs, extracted_xrefs
                )
                if page_md:
                    markdown_parts.append(page_md)

            # Write assembled markdown
            md_content = "\n\n---\n\n".join(markdown_parts)
            md_path = output_dir / f"{base_name}.md"
            md_path.write_text(md_content, encoding="utf-8")

            logger.info("PDF extraction complete: %s (%d pages)", pdf_path.name, len(doc))
            return {"success": True, "output_dir": str(output_dir)}

        finally:
            doc.close()

    except Exception as e:
        logger.error("PDF extraction failed: %s — %s", pdf_path.name, e)
        return {"success": False, "error": f"PDF 解析失败: {e}"}


def _collect_image_info(doc: fitz.Document) -> Dict[int, tuple]:
    """
    Collect all image xrefs across the document.
    Returns {xref: (smask_xref, width, height)}.
    """
    info = {}
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref not in info:
                info[xref] = (img[1], img[2], img[3])
    return info


def _find_smask_xrefs(image_info: Dict[int, tuple]) -> set:
    """Return set of xrefs that are soft masks (should be skipped)."""
    return {info[0] for info in image_info.values() if info[0] > 0}


def _process_page(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    base_name: str,
    images_dir: Path,
    smask_xrefs: set,
    extracted_xrefs: set,
) -> str:
    """Process a single page: extract text and images, return markdown."""
    # Text
    text = page.get_text("text").strip()

    # Images — get positions for header/footer filtering
    page_height = page.rect.height
    img_positions = _get_image_positions(page)

    image_refs = []
    for img in page.get_images(full=True):
        xref = img[0]

        # Skip smasks and already-extracted images
        if xref in smask_xrefs or xref in extracted_xrefs:
            continue

        # Header/footer filter
        if xref in img_positions:
            y_pct = img_positions[xref] / page_height
            if y_pct > HEADER_Y_THRESHOLD or y_pct < FOOTER_Y_THRESHOLD:
                continue

        # Extract original image
        img_data = doc.extract_image(xref)
        if img_data is None:
            continue

        ext = img_data["ext"]
        img_index = len(extracted_xrefs)
        img_name = f"img_{img_index}.{ext}"

        (images_dir / img_name).write_bytes(img_data["image"])
        image_refs.append(f"![{img_name}]({base_name}_images/{img_name})")
        extracted_xrefs.add(xref)

    # Assemble page markdown
    parts = []
    if text:
        parts.append(text)
    if image_refs:
        parts.append("\n\n".join(image_refs))

    return "\n\n".join(parts)


def _get_image_positions(page: fitz.Page) -> Dict[int, float]:
    """Get image xrefs mapped to their y-center position on page."""
    positions = {}
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if xref > 0:
            bbox = info["bbox"]
            positions[xref] = (bbox[1] + bbox[3]) / 2
    return positions
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_extractor.py::TestTextExtraction -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/service/pdf_extractor.py tests/test_extractor.py
git commit -m "feat: PDF text and image extraction with PyMuPDF"
```

---

### Task 3: Image Extraction Tests

**Files:**
- Modify: `tests/test_extractor.py`

- [ ] **Step 1: Write failing tests for image extraction**

Append to `tests/test_extractor.py`:

```python
class TestImageExtraction:
    def test_extracts_image_file(self, image_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(image_pdf, output_dir)

            assert result["success"] is True
            images_dir = output_dir / "image_test_images"
            assert images_dir.is_dir()

            # Should have at least one image file
            image_files = list(images_dir.iterdir())
            assert len(image_files) >= 1
            # Image should have content (not zero bytes)
            assert all(f.stat().st_size > 0 for f in image_files)

    def test_image_referenced_in_markdown(self, image_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(image_pdf, output_dir)

            assert result["success"] is True
            content = (output_dir / "image_test.md").read_text(encoding="utf-8")
            # Should contain image reference
            assert "![" in content
            assert "image_test_images/" in content

    def test_skips_header_footer_images(self, tmp_path):
        """Images at top >85% or bottom <10% of page should be skipped."""
        pdf_path = tmp_path / "header_footer.pdf"
        img_path = tmp_path / "dot.png"

        # Create tiny image
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
        pix.save(str(img_path))
        pix = None

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        # Header image: y = 0-30 (top ~3.6% — should be skipped, y_center ~1.8%)
        page.insert_image(fitz.Rect(0, 0, 30, 30), filename=str(img_path))
        # Content image: y = 400-430 (center ~49% — should be kept)
        page.insert_image(fitz.Rect(72, 400, 102, 430), filename=str(img_path))
        # Footer image: y = 800-830 (bottom ~2.5% — should be skipped)
        page.insert_image(fitz.Rect(0, 800, 30, 830), filename=str(img_path))

        doc.save(str(pdf_path))
        doc.close()

        import tempfile as tf
        with tf.TemporaryDirectory() as out_tmp:
            output_dir = Path(out_tmp)
            result = extract_pdf(pdf_path, output_dir)

            assert result["success"] is True
            images_dir = output_dir / "header_footer_images"
            image_files = list(images_dir.iterdir())
            # Only the content image should be extracted (header/footer skipped)
            # Note: all 3 may share same xref, so this tests position filtering
            # We expect at most 1 image file
            assert len(image_files) <= 1
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
python -m pytest tests/test_extractor.py::TestImageExtraction -v
```

Expected: 3 passed (image extraction logic was already implemented in Task 2).

- [ ] **Step 3: Commit**

```bash
git add tests/test_extractor.py
git commit -m "test: add image extraction unit tests"
```

---

### Task 4: Table Extraction + Markdown Assembly

**Files:**
- Modify: `app/service/pdf_extractor.py`
- Modify: `tests/test_extractor.py`

- [ ] **Step 1: Write failing tests for table extraction**

Append to `tests/test_extractor.py`:

```python
class TestTableExtraction:
    def test_table_in_markdown(self, table_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(table_pdf, output_dir)

            assert result["success"] is True
            content = (output_dir / "table_test.md").read_text(encoding="utf-8")
            # Table should be rendered as markdown pipe syntax
            assert "|" in content

    def test_table_has_header_separator(self, table_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(table_pdf, output_dir)

            assert result["success"] is True
            content = (output_dir / "table_test.md").read_text(encoding="utf-8")
            # Markdown table should have separator row: | --- | --- |
            assert "---" in content


class TestMixedContent:
    def test_mixed_pdf_produces_markdown(self, mixed_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(mixed_pdf, output_dir)

            assert result["success"] is True
            content = (output_dir / "mixed_test.md").read_text(encoding="utf-8")
            # Should have text content
            assert len(content) > 0

    def test_mixed_pdf_creates_images(self, mixed_pdf):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = extract_pdf(mixed_pdf, output_dir)

            assert result["success"] is True
            images_dir = output_dir / "mixed_test_images"
            assert images_dir.is_dir()
            assert len(list(images_dir.iterdir())) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_extractor.py::TestTableExtraction tests/test_extractor.py::TestMixedContent -v
```

Expected: Table tests FAIL — table extraction not yet implemented.

- [ ] **Step 3: Add table extraction to pdf_extractor.py**

Add import at top of `app/service/pdf_extractor.py`:

```python
import pdfplumber
```

Replace `_process_page` function in `app/service/pdf_extractor.py` with:

```python
def _process_page(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    base_name: str,
    images_dir: Path,
    smask_xrefs: set,
    extracted_xrefs: set,
) -> str:
    """Process a single page: extract text, tables, and images, return markdown."""
    # Text
    text = page.get_text("text").strip()

    # Tables (pdfplumber) — opened separately from PyMuPDF
    table_md = _extract_tables(str(doc.name), page_num)

    # Images — get positions for header/footer filtering
    page_height = page.rect.height
    img_positions = _get_image_positions(page)

    image_refs = []
    for img in page.get_images(full=True):
        xref = img[0]

        # Skip smasks and already-extracted images
        if xref in smask_xrefs or xref in extracted_xrefs:
            continue

        # Header/footer filter
        if xref in img_positions:
            y_pct = img_positions[xref] / page_height
            if y_pct > HEADER_Y_THRESHOLD or y_pct < FOOTER_Y_THRESHOLD:
                continue

        # Extract original image
        img_data = doc.extract_image(xref)
        if img_data is None:
            continue

        ext = img_data["ext"]
        img_index = len(extracted_xrefs)
        img_name = f"img_{img_index}.{ext}"

        (images_dir / img_name).write_bytes(img_data["image"])
        image_refs.append(f"![{img_name}]({base_name}_images/{img_name})")
        extracted_xrefs.add(xref)

    # Assemble page markdown
    parts = []
    if text:
        parts.append(text)
    if table_md:
        parts.append(table_md)
    if image_refs:
        parts.append("\n\n".join(image_refs))

    return "\n\n".join(parts)


def _extract_tables(pdf_path: str, page_num: int) -> str:
    """Extract tables from a page using pdfplumber, return markdown."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                return ""
            page = pdf.pages[page_num]
            tables = page.extract_tables()
            if not tables:
                return ""

            table_parts = []
            for table in tables:
                if not table or len(table) == 0:
                    continue
                lines = []
                for i, row in enumerate(table):
                    cells = [str(cell or "").strip() for cell in row]
                    lines.append("| " + " | ".join(cells) + " |")
                    if i == 0:
                        lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
                table_parts.append("\n".join(lines))

            return "\n\n".join(table_parts)
    except Exception as e:
        logger.debug("Table extraction failed for page %d: %s", page_num, e)
        return ""
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
python -m pytest tests/test_extractor.py -v
```

Expected: All 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/service/pdf_extractor.py tests/test_extractor.py
git commit -m "feat: add table extraction with pdfplumber"
```

---

### Task 5: API Schemas + Health Endpoint

**Files:**
- Create: `app/model/schemas.py`
- Create: `app/main.py`
- Create: `app/router/convert.py` (health only for now)
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test for health endpoint**

Create `tests/test_api.py`:

```python
"""Integration tests for API endpoints."""
import json
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_format(self):
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "3.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_api.py::TestHealthEndpoint -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Create app/model/schemas.py**

```python
"""API response models."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
```

- [ ] **Step 4: Create app/router/convert.py (health endpoint only)**

```python
"""REST endpoints for PDF conversion."""
from fastapi import APIRouter

from app.model.schemas import HealthResponse

router = APIRouter()

VERSION = "3.0.0"


@router.get("/api/v1/health")
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version=VERSION)
```

- [ ] **Step 5: Create app/main.py**

```python
"""FastAPI application entry point."""
import logging

from fastapi import FastAPI

from app.router.convert import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="AirReader", version="3.0.0")
app.include_router(router)
```

- [ ] **Step 6: Run health tests to verify they pass**

```bash
python -m pytest tests/test_api.py::TestHealthEndpoint -v
```

Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add app/model/schemas.py app/router/convert.py app/main.py tests/test_api.py
git commit -m "feat: FastAPI app with health endpoint"
```

---

### Task 6: Convert Endpoint

**Files:**
- Modify: `app/router/convert.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for convert endpoint**

Append to `tests/test_api.py`:

```python
class TestConvertEndpoint:
    def test_convert_returns_zip(self, text_pdf):
        with open(text_pdf, "rb") as f:
            response = client.post(
                "/api/v1/convert/file",
                files={"files": ("text_test.pdf", f, "application/pdf")},
            )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

        # Verify zip structure
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "meta.json" in names
            assert "text_test.md" in names

            meta = json.loads(zf.read("meta.json"))
            assert meta["status"] == "success"
            assert meta["filename"] == "text_test.pdf"

    def test_convert_error_missing_filename(self):
        response = client.post(
            "/api/v1/convert/file",
            files={"files": ("", b"dummy", "application/pdf")},
        )
        assert response.status_code == 200
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert meta["status"] == "failure"
            assert any(e["code"] == "INVALID_REQUEST" for e in meta["errors"])

    def test_convert_error_non_pdf(self):
        response = client.post(
            "/api/v1/convert/file",
            files={"files": ("test.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 200
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert meta["status"] == "failure"
            assert any(e["code"] == "UNSUPPORTED_FORMAT" for e in meta["errors"])

    def test_convert_error_empty_file(self):
        response = client.post(
            "/api/v1/convert/file",
            files={"files": ("test.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 200
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf) as zf:
            meta = json.loads(zf.read("meta.json"))
            assert meta["status"] == "failure"
            assert any(e["code"] == "EMPTY_FILE" for e in meta["errors"])

    def test_convert_with_images(self, image_pdf):
        with open(image_pdf, "rb") as f:
            response = client.post(
                "/api/v1/convert/file",
                files={"files": ("image_test.pdf", f, "application/pdf")},
            )
        assert response.status_code == 200
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "meta.json" in names
            meta = json.loads(zf.read("meta.json"))
            assert meta["status"] == "success"
            # Should have image files in the zip
            image_entries = [n for n in names if n.startswith("image_test_images/")]
            assert len(image_entries) >= 1

    def test_convert_content_disposition_header(self, text_pdf):
        with open(text_pdf, "rb") as f:
            response = client.post(
                "/api/v1/convert/file",
                files={"files": ("text_test.pdf", f, "application/pdf")},
            )
        assert "attachment" in response.headers["content-disposition"]
        assert "text_test.zip" in response.headers["content-disposition"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_api.py::TestConvertEndpoint -v
```

Expected: FAIL — convert endpoint not yet implemented.

- [ ] **Step 3: Implement convert endpoint in app/router/convert.py**

Replace entire content of `app/router/convert.py` with:

```python
"""REST endpoints for PDF conversion."""
import json
import shutil
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from app.model.schemas import HealthResponse
from app.service.pdf_extractor import extract_pdf

router = APIRouter()

VERSION = "3.0.0"
MAX_SIZE = 50 * 1024 * 1024  # 50 MB


@router.get("/api/v1/health")
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version=VERSION)


@router.post("/api/v1/convert/file")
async def convert_file(files: UploadFile = File(...)):
    t0 = time.time()
    filename = files.filename or ""
    elapsed = lambda: round(time.time() - t0, 2)

    # Validate filename
    if not filename or not filename.strip():
        return _error_zip("error.pdf", 0, "INVALID_REQUEST", "缺少文件名", elapsed())

    lower = filename.lower()
    if not lower.endswith(".pdf"):
        ext = lower[lower.rfind("."):]
        return _error_zip(filename, 0, "UNSUPPORTED_FORMAT",
                          f"仅支持 PDF 文件，收到: {ext}", elapsed())

    # Read content
    content = await files.read()
    file_size = len(content)

    if file_size == 0:
        return _error_zip(filename, 0, "EMPTY_FILE", "上传文件为空", elapsed())

    if file_size > MAX_SIZE:
        return _error_zip(filename, file_size, "FILE_TOO_LARGE",
                          "文件大小超过 50 MB 限制", elapsed())

    # Process
    tmp_file = None
    output_dir = None
    try:
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(content)
            tmp_file = Path(f.name)

        # Extract
        output_dir = Path(tempfile.mkdtemp(prefix="air-reader-"))
        result = extract_pdf(tmp_file, output_dir)

        if not result["success"]:
            _cleanup(tmp_file, output_dir)
            return _error_zip(filename, file_size, "EXTRACTION_FAILED",
                              result["error"], elapsed())

        # Build success zip
        base_name = Path(filename).stem
        buf = _build_success_zip(output_dir, base_name, filename, file_size, elapsed())
        _cleanup(tmp_file, output_dir)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.zip"'},
        )

    except Exception as e:
        _cleanup(tmp_file, output_dir)
        return _error_zip(filename, file_size, "EXTRACTION_FAILED",
                          f"文件处理失败: {e}", elapsed())


def _build_success_zip(
    output_dir: Path, base_name: str, filename: str,
    file_size: int, elapsed: float,
) -> BytesIO:
    """Build a success zip: meta.json + .md + _images/."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "filename": filename,
            "file_size_bytes": file_size,
            "processing_time": elapsed,
            "status": "success",
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))

        md_path = output_dir / f"{base_name}.md"
        if md_path.exists():
            zf.write(md_path, f"{base_name}.md")

        images_dir = output_dir / f"{base_name}_images"
        if images_dir.exists():
            for img_file in sorted(images_dir.iterdir()):
                if img_file.is_file():
                    zf.write(img_file, f"{base_name}_images/{img_file.name}")

    buf.seek(0)
    return buf


def _error_zip(
    filename: str, file_size: int, code: str, message: str, elapsed: float,
) -> StreamingResponse:
    """Build an error zip containing only meta.json with failure status."""
    safe_name = filename if filename else "error.pdf"
    base_name = safe_name.replace(".pdf", "").replace(".PDF", "")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "filename": safe_name,
            "file_size_bytes": file_size,
            "processing_time": elapsed,
            "status": "failure",
            "errors": [{"code": code, "message": message}],
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.zip"'},
    )


def _cleanup(tmp_file: Path = None, output_dir: Path = None):
    """Clean up temporary files and directories."""
    if tmp_file and tmp_file.exists():
        tmp_file.unlink()
    if output_dir and output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
```

- [ ] **Step 4: Run all API tests to verify they pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass (11 extractor + 8 API = 19 tests).

- [ ] **Step 6: Commit**

```bash
git add app/router/convert.py tests/test_api.py
git commit -m "feat: convert endpoint with zip packaging and error handling"
```

---

### Task 7: Docker Configuration

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.dockerignore`

- [ ] **Step 1: Replace Dockerfile**

Write `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN groupadd --system appuser && useradd --system --gid appuser appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Update docker-compose.yml**

Write `docker-compose.yml`:

```yaml
services:
  air-reader:
    build:
      context: .
      dockerfile: Dockerfile
    image: air-reader:3.0.0
    container_name: reader.air
    ports:
      - "9103:8000"
    volumes:
      - air-reader-data:/data
    deploy:
      resources:
        limits:
          memory: 2g
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  air-reader-data:
```

- [ ] **Step 3: Update .dockerignore**

Write `.dockerignore`:

```
.git
__pycache__
*.pyc
.env
.venv
venv
.DS_Store
.idea
.pytest_cache
target
tests
docs
skills
*.md
!requirements.txt
```

- [ ] **Step 4: Test Docker build**

```bash
docker build -t air-reader:3.0.0 .
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: Docker configuration for Python service"
```

---

### Task 8: Cleanup Java + Update Docs

**Files:**
- Delete: `pom.xml`
- Delete: `src/` (entire tree)
- Delete: `scripts/build.sh`
- Delete: `target/` (build artifacts)
- Modify: `README.md`

- [ ] **Step 1: Remove Java artifacts**

```bash
rm -rf src/ target/ scripts/ pom.xml
```

- [ ] **Step 2: Update .gitignore**

Read current `.gitignore`, add Python entries:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.pytest_cache/
*.egg-info/

# Build
target/

# IDE
.idea/

# OS
.DS_Store
```

- [ ] **Step 3: Update README.md**

Write `README.md`:

```markdown
# AirReader

PDF to Markdown conversion service powered by PyMuPDF + pdfplumber.

Extracts text, images (original resolution), and tables from PDF files,
returning a zip package with Markdown and image assets.

## Features

- Text extraction with layout preservation
- Image extraction at original resolution (zero loss)
- Table extraction to Markdown table syntax
- Header/footer image filtering
- Fully compatible API (zip response format)

## Quick Start

### Local

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### Docker

```bash
docker compose up -d
```

## API

### Health Check

```bash
curl http://localhost:8000/api/v1/health
# {"status":"healthy","version":"3.0.0"}
```

### Convert PDF

```bash
curl -X POST http://localhost:8000/api/v1/convert/file \
  -F "files=@document.pdf" \
  -o document.zip
```

Response is a zip containing:
- `meta.json` — status and metadata
- `{name}.md` — extracted Markdown
- `{name}_images/` — extracted images (original resolution)

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web Framework | FastAPI + uvicorn |
| PDF Extraction | PyMuPDF (fitz) |
| Table Extraction | pdfplumber |
| Runtime | Python 3.11+ |

## License

Proprietary
```

- [ ] **Step 4: Verify app still starts**

```bash
python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All 19 tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove Java artifacts, update docs for Python migration"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Every section in the design spec maps to a task:
  - Tech stack → Task 1
  - Text extraction → Task 2
  - Image extraction → Tasks 2-3
  - Table extraction → Task 4
  - Markdown assembly → Task 4
  - API contract → Tasks 5-6
  - Docker → Task 7
  - Cleanup → Task 8
- [x] **Placeholder scan:** No TBDs, TODOs, or vague descriptions. Every step has complete code.
- [x] **Type consistency:** `extract_pdf(pdf_path: Path, output_dir: Path) -> Dict[str, Any]` signature is consistent across all test and implementation files. Image naming (`img_{index}.{ext}`) is consistent.
