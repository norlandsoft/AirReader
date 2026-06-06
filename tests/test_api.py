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
