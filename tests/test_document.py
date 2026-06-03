"""Tests for the standardized AirFileReader API."""

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.open_data_loader import OpenDataLoader, get_loader

client = TestClient(app)


def _extract(content: bytes, filename: str, **params):
    return client.post(
        "/api/v1/documents/extract",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        params=params,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["status"] == "healthy"

    def test_health_has_envelope(self):
        resp = client.get("/api/v1/health")
        body = resp.json()
        assert "metadata" in body
        assert "request_id" in body["metadata"]
        assert body["errors"] == []


# ---------------------------------------------------------------------------
# Document extraction — success
# ---------------------------------------------------------------------------

class TestExtractSuccess:
    def test_extract_txt(self):
        resp = _extract(b"Hello, world!", "test.txt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["document"]["filename"] == "test.txt"
        assert data["document"]["type"] == "Text"
        assert data["document"]["format"] == "txt"
        assert "Hello, world!" in data["content"]["text"]
        assert data["content"]["format"] == "markdown"
        assert body["metadata"]["processing_time_ms"] > 0

    def test_extract_md(self):
        resp = _extract(b"# Title\n\nBody", "doc.md")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "# Title" in data["content"]["text"]

    def test_extract_text_output_format(self):
        resp = _extract(b"**bold** and *italic* text.", "note.md", output_format="text")
        assert resp.status_code == 200
        text = resp.json()["data"]["content"]["text"]
        assert "bold" in text
        assert "italic" in text
        assert "**" not in text  # stripped
        assert resp.json()["data"]["content"]["format"] == "text"

    def test_extract_has_request_id(self):
        resp = _extract(b"test", "a.txt")
        rid = resp.json()["metadata"]["request_id"]
        assert len(rid) == 32

    def test_extract_custom_request_id(self):
        resp = client.post(
            "/api/v1/documents/extract",
            files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")},
            headers={"X-Request-ID": "my-custom-id"},
        )
        rid = resp.json()["metadata"]["request_id"]
        assert rid == "my-custom-id"


# ---------------------------------------------------------------------------
# Document extraction — errors
# ---------------------------------------------------------------------------

class TestExtractErrors:
    def test_empty_file(self):
        resp = _extract(b"", "empty.txt")
        assert resp.status_code == 400
        body = resp.json()
        assert body["status"] == "error"
        assert body["data"] is None
        assert body["errors"][0]["code"] == "EMPTY_FILE"

    def test_unsupported_format(self):
        resp = _extract(b"data", "file.exe")
        assert resp.status_code == 415
        body = resp.json()
        assert body["status"] == "error"
        assert body["errors"][0]["code"] == "UNSUPPORTED_FORMAT"

    def test_no_filename(self):
        # FastAPI may validate this at 422 (validation) or our code at 400 —
        # both are acceptable; we just check the envelope shape.
        resp = client.post(
            "/api/v1/documents/extract",
            files={"file": ("", io.BytesIO(b"x"), "text/plain")},
        )
        assert resp.status_code in (400, 422)
        body = resp.json()
        assert body["status"] == "error"
        assert body["data"] is None
        assert len(body["errors"]) >= 1
        assert "request_id" in body["metadata"]


# ---------------------------------------------------------------------------
# Store & retrieve
# ---------------------------------------------------------------------------

class TestStoreRetrieve:
    def test_store(self):
        resp = _extract(b"stored", "doc.md", store="true")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_retrieve_not_found(self):
        resp = client.get("/api/v1/documents/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["status"] == "error"
        assert body["errors"][0]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# OpenDataLoader unit
# ---------------------------------------------------------------------------

class TestOpenDataLoader:
    def test_extract_bytes(self):
        loader = OpenDataLoader()
        result = loader.extract_bytes(b"Plain text.", "note.txt")
        assert "Plain text." in result.markdown

    def test_file_not_found(self):
        loader = OpenDataLoader()
        with pytest.raises(FileNotFoundError):
            loader.extract("/no/such/file.pdf")

    def test_singleton(self):
        assert get_loader() is get_loader()


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["service"] == "AirFileReader"
