"""Document extraction API routes — PDF-only, powered by opendataloader-pdf."""

import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from app.models import (
    ApiError,
    ApiResponse,
    ContentInfo,
    DocumentInfo,
    ErrorCode,
    ExtractionData,
    HealthData,
)
from app.open_data_loader import ExtractionError, get_loader

router = APIRouter(tags=["documents"])

_doc_store: dict[str, ExtractionData] = {}

ALLOWED_EXTENSIONS = sorted({".pdf"})
SUPPORTED_FORMATS_HELP = ", ".join(e.lstrip(".") for e in ALLOWED_EXTENSIONS)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req_id(request: Request) -> str:
    return request.headers.get("X-Request-ID", uuid.uuid4().hex)


def _err(code: ErrorCode, message: str, detail: Optional[str] = None) -> ApiError:
    return ApiError(code=code, message=message, detail=detail)


def _fail(request: Request, status_code: int, errors: list[ApiError]) -> ApiResponse:
    body = ApiResponse.error(errors=errors, request_id=_req_id(request))
    raise HTTPException(status_code=status_code, detail=body.model_dump())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=ApiResponse)
async def health_check(request: Request):
    return ApiResponse.success(data=HealthData().model_dump(), request_id=_req_id(request))


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

@router.post(
    "/documents/extract",
    response_model=ApiResponse,
    summary="Extract PDF content via OpenDataLoader",
    description="Upload a PDF file and receive its content extracted as Markdown using the opendataloader-pdf library.",
)
async def extract_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file to extract (max 50 MB)."),
    output_format: str = Query(
        "markdown",
        alias="output_format",
        description="Output format: 'markdown' or 'text'.",
        pattern=r"^(markdown|text)$",
    ),
    store: bool = Query(False, description="Store result for later retrieval."),
):
    t0 = time.perf_counter()

    if not file.filename:
        return _fail(request, 400, [_err(ErrorCode.INVALID_REQUEST, "No filename provided.")])

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return _fail(request, 415, [_err(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"File type '{suffix or 'unknown'}' is not supported.",
            detail=f"OpenDataLoader only supports PDF files ({SUPPORTED_FORMATS_HELP}).",
        )])

    content = await file.read()
    if not content:
        return _fail(request, 400, [_err(ErrorCode.EMPTY_FILE, "Uploaded file is empty.")])

    if len(content) > MAX_FILE_SIZE:
        return _fail(request, 413, [_err(
            ErrorCode.FILE_TOO_LARGE,
            f"File size {len(content)} exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
        )])

    loader = get_loader()
    try:
        result = loader.extract_bytes(content=content, filename=file.filename)
    except ExtractionError as exc:
        return _fail(request, 500, [_err(ErrorCode.EXTRACTION_FAILED, str(exc))])
    except Exception as exc:
        return _fail(request, 500, [_err(
            ErrorCode.EXTRACTION_FAILED, "Document extraction failed.", detail=str(exc),
        )])

    doc_info = DocumentInfo(
        filename=result.filename,
        format="pdf",
        type="PDF",
        page_count=result.page_count,
        file_size_bytes=result.file_size_bytes,
    )

    text = result.markdown
    if output_format == "text":
        text = _strip_markdown(text)

    content_info = ContentInfo(format=output_format, text=text, length=len(text))
    data = ExtractionData(document=doc_info, content=content_info)

    if store:
        doc_id = uuid.uuid4().hex
        _doc_store[doc_id] = data

    elapsed = (time.perf_counter() - t0) * 1000
    return ApiResponse.success(data=data.model_dump(), request_id=_req_id(request), processing_time_ms=elapsed)


# ---------------------------------------------------------------------------
# Retrieve stored document
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}", response_model=ApiResponse, summary="Retrieve a stored document")
async def get_document(request: Request, doc_id: str):
    data = _doc_store.get(doc_id)
    if data is None:
        return _fail(request, 404, [_err(ErrorCode.NOT_FOUND, f"Document '{doc_id}' not found.")])
    return ApiResponse.success(data=data.model_dump(), request_id=_req_id(request))


# ---------------------------------------------------------------------------
# Markdown → plain text stripper
# ---------------------------------------------------------------------------

import re as _re

def _strip_markdown(text: str) -> str:
    text = _re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = _re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = _re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    text = _re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)
    text = _re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = _re.sub(r"(?m)^>\s?", "", text)
    text = _re.sub(r"(?m)^[-*_]{3,}\s*$", "", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
