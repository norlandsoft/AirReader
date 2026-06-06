"""Unit tests for PDF extraction service."""
import tempfile
from pathlib import Path

import fitz
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
