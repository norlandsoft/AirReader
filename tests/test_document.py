"""Tests for the OpenDataLoader-powered AirFileReader API (PDF only)."""

import io
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.open_data_loader import ExtractionError, OpenDataLoader, get_loader

client = TestClient(app)


def _upload(content: bytes, filename: str, **params):
    return client.post(
        "/api/v1/documents/extract",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        params=params,
    )


def _sample_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 72), "Hello from test PDF!", fontsize=12)
    out = doc.tobytes()
    doc.close()
    return out


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["status"] == "healthy"

    def test_has_envelope(self):
        resp = client.get("/api/v1/health")
        body = resp.json()
        assert "metadata" in body
        assert "request_id" in body["metadata"]
        assert body["errors"] == []


# ---------------------------------------------------------------------------
# PDF extraction — success
# ---------------------------------------------------------------------------

class TestExtractPdf:
    def test_extract_pdf(self):
        resp = _upload(_sample_pdf(), "test.pdf")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["document"]["filename"] == "test.pdf"
        assert data["document"]["type"] == "PDF"
        assert data["document"]["page_count"] > 0
        assert "Hello from test PDF!" in data["content"]["text"]
        assert resp.json()["metadata"]["processing_time_ms"] > 0

    def test_output_text_format(self):
        resp = _upload(_sample_pdf(), "test.pdf", output_format="text")
        assert resp.status_code == 200
        assert resp.json()["data"]["content"]["format"] == "text"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestExtractErrors:
    def test_empty_file(self):
        resp = _upload(b"", "empty.pdf")
        assert resp.status_code == 400
        assert resp.json()["errors"][0]["code"] == "EMPTY_FILE"

    def test_unsupported_format(self):
        resp = client.post(
            "/api/v1/documents/extract",
            files={"file": ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")},
        )
        assert resp.status_code == 415
        assert resp.json()["errors"][0]["code"] == "UNSUPPORTED_FORMAT"

    def test_non_pdf_rejected(self):
        resp = client.post(
            "/api/v1/documents/extract",
            files={"file": ("a.txt", io.BytesIO(b"text"), "text/plain")},
        )
        assert resp.status_code == 415
        assert "UNSUPPORTED_FORMAT" == resp.json()["errors"][0]["code"]

    def test_no_filename(self):
        resp = client.post(
            "/api/v1/documents/extract",
            files={"file": ("", io.BytesIO(b"x"), "application/pdf")},
        )
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Store & retrieve
# ---------------------------------------------------------------------------

class TestStoreRetrieve:
    def test_store(self):
        resp = _upload(_sample_pdf(), "doc.pdf", store="true")
        assert resp.status_code == 200

    def test_not_found(self):
        resp = client.get("/api/v1/documents/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["errors"][0]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# OpenDataLoader unit
# ---------------------------------------------------------------------------

class TestOpenDataLoader:
    def test_extract_pdf_bytes(self):
        loader = OpenDataLoader()
        result = loader.extract_bytes(_sample_pdf(), "test.pdf")
        assert "Hello from test PDF!" in result.markdown

    def test_file_not_found(self):
        loader = OpenDataLoader()
        with pytest.raises(FileNotFoundError):
            loader.extract("/no/such/file.pdf")

    def test_non_pdf_rejected(self):
        loader = OpenDataLoader()
        with pytest.raises(ExtractionError):
            loader.extract_bytes(b"text", "note.txt")


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["service"] == "AirFileReader"
