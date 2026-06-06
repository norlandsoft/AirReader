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
    pix.set_rect(pix.irect, (255, 0, 0))  # solid red
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
    pix.set_rect(pix.irect, (255, 0, 0))
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
    doc.save(str(pdf_path), incremental=True, encryption=0)
    doc.close()

    return pdf_path
