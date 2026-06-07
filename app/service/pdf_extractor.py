"""
PDF extraction service using PyMuPDF + pdfplumber.

Extracts text, images (original resolution), and tables from PDF files,
assembling them into Markdown format — preserving the original reading order.
"""
import io
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)

FOOTER_Y_THRESHOLD = 0.85  # Bottom 15% of page
HEADER_Y_THRESHOLD = 0.10  # Top 10% of page
PAGE_NUM_RE = re.compile(r'^\d+\s*/\s*\d+$')


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
            # Pre-scan 1: image info (smask detection)
            image_info = _collect_image_info(doc)
            smask_xrefs = _find_smask_xrefs(image_info)

            # Pre-scan 2: detect repeating page headers/footers
            header_footer_texts = _detect_headers_footers(doc)
            if header_footer_texts:
                logger.info("Filtered headers/footers: %d patterns", len(header_footer_texts))

            markdown_parts = []
            extracted_xrefs = set()

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_md = _process_page(
                    doc, page, page_num, base_name, images_dir,
                    smask_xrefs, extracted_xrefs,
                    header_footer_texts, image_info,
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


# ── Pre-scan helpers ───────────────────────────────────────────────────

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


def _detect_headers_footers(doc: fitz.Document) -> Set[str]:
    """
    Detect text blocks that repeat at consistent positions across pages.
    Returns a set of text strings to filter out as headers/footers.
    """
    total_pages = len(doc)
    if total_pages < 3:
        return set()

    freq: Dict[str, int] = {}

    for page_num in range(total_pages):
        page = doc[page_num]
        page_height = page.rect.height
        text_dict = page.get_text("dict")

        for block in text_dict["blocks"]:
            if block["type"] != 0:
                continue
            y_center = (block["bbox"][1] + block["bbox"][3]) / 2
            # Only consider text in header or footer zones
            y_pct = y_center / page_height
            if y_pct > HEADER_Y_THRESHOLD and y_pct < FOOTER_Y_THRESHOLD:
                continue  # Not in header/footer zone

            text = _block_text(block).strip()
            if text:
                freq[text] = freq.get(text, 0) + 1

    threshold = max(3, total_pages * 0.5)
    return {text for text, count in freq.items() if count >= threshold}


# ── Page processing ───────────────────────────────────────────────────

def _process_page(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    base_name: str,
    images_dir: Path,
    smask_xrefs: set,
    extracted_xrefs: set,
    header_footer_texts: Set[str],
    image_info: Dict[int, tuple],
) -> str:
    """Process a single page: extract text, tables, and images in reading order (top to bottom)."""
    logger.debug("Processing page %d", page_num)
    page_height = page.rect.height

    # ── 1. Table regions (pdfplumber) — bounding boxes + markdown ──
    table_regions = _find_table_regions(str(doc.name), page_num)

    # ── 2. Text blocks with Y positions, excluding tables and headers/footers ──
    content_elements: List[Tuple[float, str, str]] = []
    text_dict = page.get_text("dict")

    for block in text_dict["blocks"]:
        if block["type"] != 0:
            continue
        bbox = block["bbox"]
        if _overlaps_table(bbox, table_regions):
            continue
        text = _block_text(block).strip()
        if not text:
            continue
        # Skip detected headers/footers and page number patterns
        if _is_header_footer(text, header_footer_texts):
            continue
        y_center = (bbox[1] + bbox[3]) / 2
        content_elements.append((y_center, "text", text))

    # ── 3. Tables at their Y positions ─────────────────────────────
    for tbl in table_regions:
        content_elements.append((tbl["y_center"], "table", tbl["markdown"]))

    # ── 4. Images at their Y positions ─────────────────────────────
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if xref <= 0:
            continue

        # Skip smasks and already-extracted images
        if xref in smask_xrefs or xref in extracted_xrefs:
            continue

        bbox = info["bbox"]
        y_center = (bbox[1] + bbox[3]) / 2

        # Header/footer filter
        y_pct = y_center / page_height
        if y_pct < HEADER_Y_THRESHOLD or y_pct > FOOTER_Y_THRESHOLD:
            continue

        # Extract image with smask compositing
        img_result = _extract_image_data(doc, xref, image_info)
        if img_result is None:
            continue

        ext = img_result["ext"]
        img_bytes = img_result["image"]
        img_index = len(extracted_xrefs)
        img_name = f"img_{img_index}.{ext}"

        (images_dir / img_name).write_bytes(img_bytes)
        img_ref = f"![{img_name}]({base_name}_images/{img_name})"
        extracted_xrefs.add(xref)

        content_elements.append((y_center, "image", img_ref))

    # ── 5. Sort all elements by Y position (top → bottom) ─────────
    content_elements.sort(key=lambda e: e[0])

    # ── 6. Build markdown ─────────────────────────────────────────
    parts = [elem[2] for elem in content_elements if elem[2].strip()]
    return "\n\n".join(parts)


# ── Image extraction ──────────────────────────────────────────────────

def _extract_image_data(
    doc: fitz.Document,
    xref: int,
    image_info: Dict[int, tuple],
) -> Dict[str, Any] | None:
    """
    Extract image, properly compositing smask (soft mask) onto white background.

    - Images WITHOUT smask: raw extraction via doc.extract_image() (fast, preserves format)
    - Images WITH smask: manually composite smask as alpha → white background via PIL
    """
    smask_xref = image_info.get(xref, (0, 0, 0))[0]

    if smask_xref == 0:
        # No smask — raw extraction preserves original format and quality
        return doc.extract_image(xref)

    # Has smask — manually extract image + smask and composite onto white
    try:
        from PIL import Image

        # Extract image and its smask separately
        img_data = doc.extract_image(xref)
        smask_data = doc.extract_image(smask_xref)

        img = Image.open(io.BytesIO(img_data["image"]))
        mask = Image.open(io.BytesIO(smask_data["image"]))

        # Apply smask as alpha channel
        img = img.convert("RGBA")
        mask = mask.convert("L")  # grayscale → alpha
        img.putalpha(mask)

        # Composite onto white background
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        result = bg.convert("RGB")

        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=95)
        return {
            "image": buf.getvalue(),
            "ext": "jpeg",
            "width": result.width,
            "height": result.height,
        }

    except Exception as e:
        logger.debug("Smask compositing failed for xref %d, falling back: %s", xref, e)
        return doc.extract_image(xref)


# ── Text helpers ───────────────────────────────────────────────────────

def _block_text(block: dict) -> str:
    """Extract text from a get_text("dict") block."""
    lines = []
    for line in block.get("lines", []):
        spans = [span["text"] for span in line.get("spans", [])]
        lines.append("".join(spans))
    return "\n".join(lines)


def _is_header_footer(text: str, header_footer_set: Set[str]) -> bool:
    """Check if text is a detected header/footer or a page number pattern."""
    stripped = text.strip()
    if stripped in header_footer_set:
        return True
    if PAGE_NUM_RE.match(stripped):
        return True
    return False


# ── Table helpers ──────────────────────────────────────────────────────

def _find_table_regions(pdf_path: str, page_num: int) -> List[Dict]:
    """
    Find table bounding boxes and extract as markdown using pdfplumber.

    Returns list of {"bbox": (x0,y0,x1,y1), "y_center": float, "markdown": str}.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                return []
            page = pdf.pages[page_num]
            tables = page.find_tables()
            result = []
            for table in tables:
                bbox = table.bbox
                y_center = (bbox[1] + bbox[3]) / 2
                table_data = table.extract()
                if not _is_likely_table(table_data):
                    continue
                md = _table_to_markdown(table_data)
                if md:
                    result.append({
                        "bbox": bbox,
                        "y_center": y_center,
                        "markdown": md,
                    })
            return result
    except Exception as e:
        logger.debug("Table detection failed for page %d: %s", page_num, e)
        return []


def _is_likely_table(table_data) -> bool:
    """
    Filter false-positive table detections from pdfplumber.

    pdfplumber sometimes misidentifies wrapped paragraph text as a table.
    Heuristic: real tables have short header labels; false positives have
    long cells in every row (continuous paragraph text split across columns).
    """
    if not table_data or len(table_data) < 2:
        return False

    first_row = table_data[0]
    if not first_row:
        return False

    # Average cell length in the header row
    header_avg = sum(len(str(cell or "").strip()) for cell in first_row) / len(first_row)

    # Real table headers are short labels; long "headers" are wrapped text
    if header_avg > 15:
        return False

    # For very small tables (≤2 data rows), also check that not ALL cells are long
    if len(table_data) <= 3:
        all_cells = [str(cell or "").strip() for row in table_data for cell in row]
        avg_all = sum(len(c) for c in all_cells) / len(all_cells) if all_cells else 0
        if avg_all > 20:
            return False

    return True


def _table_to_markdown(table_data) -> str:
    """
    Convert pdfplumber table data to Markdown, handling edge cases:
    - Escape | characters in cells
    - Replace newlines with spaces
    - Normalize column count across rows
    """
    if not table_data or len(table_data) == 0:
        return ""

    max_cols = max(len(row) for row in table_data)
    if max_cols == 0:
        return ""

    lines = []
    for i, row in enumerate(table_data):
        cells = []
        for cell in row:
            text = str(cell or "").strip()
            text = text.replace("|", "\\|")
            text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
            while "  " in text:
                text = text.replace("  ", " ")
            cells.append(text)
        while len(cells) < max_cols:
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    return "\n".join(lines)


def _overlaps_table(bbox: tuple, table_regions: List[Dict]) -> bool:
    """Check if a text block bbox significantly overlaps with any table region."""
    for tbl in table_regions:
        t_bbox = tbl["bbox"]
        if not (bbox[1] < t_bbox[3] and bbox[3] > t_bbox[1]):
            continue
        overlap_x0 = max(bbox[0], t_bbox[0])
        overlap_x1 = min(bbox[2], t_bbox[2])
        block_width = bbox[2] - bbox[0]
        if block_width <= 0:
            continue
        overlap_ratio = (overlap_x1 - overlap_x0) / block_width
        if overlap_ratio > 0.5:
            return True
    return False
