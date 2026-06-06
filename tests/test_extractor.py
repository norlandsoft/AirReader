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
