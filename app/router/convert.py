"""REST endpoints for PDF conversion."""
import json
import shutil
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from app.model.schemas import HealthResponse
from app.service.pdf_extractor import extract_pdf

router = APIRouter()

VERSION = "3.0.0"
MAX_SIZE = 50 * 1024 * 1024  # 50 MB


@router.get("/api/v1/health")
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version=VERSION)


@router.post("/api/v1/convert/file")
async def convert_file(files: UploadFile = File(...)):
    t0 = time.time()
    filename = files.filename or ""
    elapsed = lambda: round(time.time() - t0, 2)

    # Validate filename
    if not filename or not filename.strip():
        return _error_zip("error.pdf", 0, "INVALID_REQUEST", "缺少文件名", elapsed())

    lower = filename.lower()
    if not lower.endswith(".pdf"):
        ext = lower[lower.rfind("."):]
        return _error_zip(filename, 0, "UNSUPPORTED_FORMAT",
                          f"仅支持 PDF 文件，收到: {ext}", elapsed())

    # Read content
    content = await files.read()
    file_size = len(content)

    if file_size == 0:
        return _error_zip(filename, 0, "EMPTY_FILE", "上传文件为空", elapsed())

    if file_size > MAX_SIZE:
        return _error_zip(filename, file_size, "FILE_TOO_LARGE",
                          "文件大小超过 50 MB 限制", elapsed())

    # Process
    tmp_file = None
    output_dir = None
    try:
        # Save to temp file — use original stem so extract_pdf outputs match
        base_name = Path(filename).stem
        tmp_dir = Path(tempfile.mkdtemp(prefix="air-parser-upload-"))
        tmp_file = tmp_dir / filename
        tmp_file.write_bytes(content)

        # Extract
        output_dir = Path(tempfile.mkdtemp(prefix="air-parser-"))
        result = extract_pdf(tmp_file, output_dir)

        if not result["success"]:
            _cleanup(tmp_dir, output_dir)
            return _error_zip(filename, file_size, "EXTRACTION_FAILED",
                              result["error"], elapsed())

        # Build success zip
        buf = _build_success_zip(output_dir, base_name, filename, file_size, elapsed())
        _cleanup(tmp_dir, output_dir)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": _content_disposition(base_name)},
        )

    except Exception as e:
        _cleanup(tmp_dir, output_dir)
        return _error_zip(filename, file_size, "EXTRACTION_FAILED",
                          f"文件处理失败: {e}", elapsed())


def _build_success_zip(
    output_dir: Path, base_name: str, filename: str,
    file_size: int, elapsed: float,
) -> BytesIO:
    """Build a success zip: meta.json + .md + _images/."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "filename": filename,
            "file_size_bytes": file_size,
            "processing_time": elapsed,
            "status": "success",
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))

        md_path = output_dir / f"{base_name}.md"
        if md_path.exists():
            zf.write(md_path, f"{base_name}.md")

        images_dir = output_dir / f"{base_name}_images"
        if images_dir.exists():
            for img_file in sorted(images_dir.iterdir()):
                if img_file.is_file():
                    zf.write(img_file, f"{base_name}_images/{img_file.name}")

    buf.seek(0)
    return buf


def _error_zip(
    filename: str, file_size: int, code: str, message: str, elapsed: float,
) -> StreamingResponse:
    """Build an error zip containing only meta.json with failure status."""
    safe_name = filename if filename else "error.pdf"
    base_name = safe_name.replace(".pdf", "").replace(".PDF", "")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "filename": safe_name,
            "file_size_bytes": file_size,
            "processing_time": elapsed,
            "status": "failure",
            "errors": [{"code": code, "message": message}],
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(base_name)},
    )


def _content_disposition(base_name: str) -> str:
    """Build Content-Disposition header with RFC 5987 UTF-8 encoding for non-ASCII names."""
    ascii_name = quote(f"{base_name}.zip", safe="")
    try:
        base_name.encode("latin-1")
        return f'attachment; filename="{base_name}.zip"; filename*=UTF-8\'\'{ascii_name}'
    except UnicodeEncodeError:
        return f"attachment; filename=output.zip; filename*=UTF-8''{ascii_name}"


def _cleanup(tmp_dir: Path = None, output_dir: Path = None):
    """Clean up temporary files and directories."""
    if tmp_dir and tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    if output_dir and output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
