"""OpenDataLoader — PDF content extraction via opendataloader-pdf.

Uses the official opendataloader-pdf library (https://opendataloader.org)
for PDF-to-Markdown conversion. No fallback — failures are returned as errors.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from opendataloader_pdf import convert


class ExtractionError(Exception):
    """Raised when document extraction fails — propagated directly to the API."""
    pass


@dataclass
class DocumentResult:
    """Result of a PDF extraction via OpenDataLoader."""
    filename: str
    markdown: str
    page_count: int = 0
    file_size_bytes: int = 0


class OpenDataLoader:
    """Service that extracts PDF content using the opendataloader-pdf library.

    Only PDF files are supported. All other formats are rejected.
    """

    _pdf_suffixes = frozenset({".pdf"})

    def extract(self, file_path: str | Path, original_filename: Optional[str] = None) -> DocumentResult:
        """Extract text from a PDF file and return as Markdown.

        Args:
            file_path: Path to the PDF file on disk.
            original_filename: Original filename for metadata.

        Returns:
            DocumentResult with markdown content.

        Raises:
            FileNotFoundError: If the file does not exist.
            ExtractionError: If extraction fails for any reason.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = original_filename or file_path.name
        file_size = file_path.stat().st_size
        suffix = file_path.suffix.lower()

        if suffix not in self._pdf_suffixes:
            raise ExtractionError(
                f"Unsupported format '{suffix}'. OpenDataLoader only supports PDF files."
            )

        # --- Convert via opendataloader-pdf ---
        outdir = tempfile.mkdtemp(prefix="odl_")
        try:
            convert(str(file_path), output_dir=outdir, format=["markdown"], quiet=True)
        except Exception as exc:
            raise ExtractionError(f"OpenDataLoader conversion failed: {exc}") from exc

        # --- Read the generated markdown file ---
        stem = file_path.stem
        md_path = os.path.join(outdir, f"{stem}.md")
        if not os.path.exists(md_path):
            raise ExtractionError(
                "OpenDataLoader did not produce a markdown output file."
            )

        try:
            markdown_text = Path(md_path).read_text(encoding="utf-8")
        except Exception as exc:
            raise ExtractionError(f"Failed to read markdown output: {exc}") from exc

        # --- Page count ---
        page_count = self._count_pdf_pages(file_path)

        return DocumentResult(
            filename=filename,
            markdown=markdown_text,
            page_count=page_count,
            file_size_bytes=file_size,
        )

    def extract_bytes(self, content: bytes, filename: str) -> DocumentResult:
        """Extract text from in-memory PDF bytes.

        Args:
            content: Raw file bytes (must be a PDF).
            filename: Original filename.

        Returns:
            DocumentResult with markdown content.

        Raises:
            ExtractionError: If the content is not a valid PDF or extraction fails.
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in self._pdf_suffixes:
            raise ExtractionError(
                f"Unsupported format '{suffix}'. OpenDataLoader only supports PDF files."
            )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            return self.extract(tmp_path, original_filename=filename)
        finally:
            os.unlink(tmp_path)

    @staticmethod
    def _count_pdf_pages(file_path: Path) -> int:
        """Count pages in a PDF using pymupdf."""
        try:
            import fitz
            doc = fitz.open(str(file_path))
            count = doc.page_count
            doc.close()
            return count
        except Exception:
            return 0


_loader: Optional[OpenDataLoader] = None


def get_loader() -> OpenDataLoader:
    global _loader
    if _loader is None:
        _loader = OpenDataLoader()
    return _loader
