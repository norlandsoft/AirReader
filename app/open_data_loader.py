"""OpenDataLoader — extract document content and convert to Markdown."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from markitdown import MarkItDown
from markitdown._markitdown import UnsupportedFormatException


@dataclass
class DocumentResult:
    """Result of a document extraction."""
    filename: str
    markdown: str
    metadata: dict
    page_count: int = 0
    file_size_bytes: int = 0


class OpenDataLoader:
    """Service that loads documents and converts them to Markdown."""

    # Formats handled natively as plain text (no conversion needed)
    _plain_formats = frozenset({".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"})

    _suffix_map = {
        ".pdf": "PDF",
        ".docx": "Word",
        ".doc": "Word",
        ".pptx": "PowerPoint",
        ".ppt": "PowerPoint",
        ".xlsx": "Excel",
        ".xls": "Excel",
        ".csv": "CSV",
        ".html": "HTML",
        ".htm": "HTML",
        ".txt": "Text",
        ".md": "Markdown",
        ".json": "JSON",
        ".xml": "XML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".jpg": "Image",
        ".jpeg": "Image",
        ".png": "Image",
    }

    def __init__(self):
        self._converter = MarkItDown()

    def extract(self, file_path: str | Path, original_filename: Optional[str] = None) -> DocumentResult:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = original_filename or file_path.name
        file_size = file_path.stat().st_size
        suffix = file_path.suffix.lower()
        doc_type = self._suffix_map.get(suffix, "Unknown")

        if suffix in self._plain_formats:
            text = file_path.read_text(encoding="utf-8")
            return self._result(filename, text, doc_type, suffix, file_size)

        try:
            result = self._converter.convert(str(file_path))
        except UnsupportedFormatException:
            text = file_path.read_text(encoding="utf-8")
            return self._result(filename, text, doc_type, suffix, file_size)

        page_count = 0
        if suffix == ".pdf":
            page_count = self._count_pdf_pages(file_path)

        return DocumentResult(
            filename=filename,
            markdown=result.text_content,
            metadata={"type": doc_type, "format": suffix.lstrip("."), "source": filename},
            page_count=page_count,
            file_size_bytes=file_size,
        )

    def extract_bytes(self, content: bytes, filename: str, suffix: Optional[str] = None) -> DocumentResult:
        if suffix is None:
            suffix = Path(filename).suffix
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            return self.extract(tmp_path, original_filename=filename)
        finally:
            os.unlink(tmp_path)

    @staticmethod
    def _result(filename: str, text: str, doc_type: str, suffix: str, file_size: int) -> DocumentResult:
        return DocumentResult(
            filename=filename,
            markdown=text,
            metadata={"type": doc_type, "format": suffix.lstrip("."), "source": filename},
            page_count=0,
            file_size_bytes=file_size,
        )

    @staticmethod
    def _count_pdf_pages(file_path: Path) -> int:
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
