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
