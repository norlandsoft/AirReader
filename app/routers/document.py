"""Document extraction API routes — standardized request/response format."""

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
from app.open_data_loader import get_loader

router = APIRouter(tags=["documents"])

# In-memory store for extracted documents (production would use a DB/cache)
_doc_store: dict[str, ExtractionData] = {}

ALLOWED_EXTENSIONS = sorted(
    {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
     ".csv", ".html", ".htm", ".txt", ".md", ".jpg", ".jpeg", ".png"}
)

SUPPORTED_FORMATS_HELP = ", ".join(e.lstrip(".") for e in ALLOWED_EXTENSIONS)

# 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request_id(request: Request) -> str:
    # Prefer an incoming X-Request-ID header; generate one otherwise
    return request.headers.get("X-Request-ID", uuid.uuid4().hex)


def _api_error(code: ErrorCode, message: str, detail: Optional[str] = None) -> ApiError:
    return ApiError(code=code, message=message, detail=detail)


def _error_response(
    request: Request,
    status_code: int,
    errors: list[ApiError],
    elapsed: float = 0.0,
) -> ApiResponse:
    body = ApiResponse.error(errors=errors, request_id=_request_id(request), processing_time_ms=elapsed)
    # We rely on FastAPI exception handling for the HTTP status code,
    # but return the envelope as the body.
    raise HTTPException(status_code=status_code, detail=body.model_dump())


# ---------------------------------------------------------------------------
# Middleware hook — attach request_id and timer to request.state
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=ApiResponse)
async def health_check(request: Request):
    return ApiResponse.success(
        data=HealthData().model_dump(),
        request_id=_request_id(request),
    )


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

@router.post(
    "/documents/extract",
    response_model=ApiResponse,
    summary="Extract document content",
    description=(
        "Upload a document file and receive its content extracted as Markdown "
        "or plain text. Supports PDF, Word, PowerPoint, Excel, HTML, "
        "plain text, Markdown, and images."
    ),
)
async def extract_document(
    request: Request,
    file: UploadFile = File(..., description="Document file to extract (max 50 MB)."),
    output_format: str = Query(
        "markdown",
        alias="output_format",
        description="Desired output format: 'markdown' or 'text'.",
        pattern=r"^(markdown|text)$",
    ),
    store: bool = Query(False, description="If true, store the result for later retrieval."),
):
    t0 = time.perf_counter()

    # --- validate filename ---
    if not file.filename:
        return _error_response(
            request=request,
            status_code=400,
            errors=[_api_error(ErrorCode.INVALID_REQUEST, "No filename provided.")],
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return _error_response(
            request=request,
            status_code=415,
            errors=[_api_error(
                ErrorCode.UNSUPPORTED_FORMAT,
                f"File type '{suffix or 'unknown'}' is not supported.",
                detail=f"Supported formats: {SUPPORTED_FORMATS_HELP}.",
            )],
        )

    # --- read content ---
    content = await file.read()
    if not content:
        return _error_response(
            request=request,
            status_code=400,
            errors=[_api_error(ErrorCode.EMPTY_FILE, "Uploaded file is empty.")],
        )

    if len(content) > MAX_FILE_SIZE:
        return _error_response(
            request=request,
            status_code=413,
            errors=[_api_error(
                ErrorCode.FILE_TOO_LARGE,
                f"File size {len(content)} exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
            )],
        )

    # --- extract ---
    loader = get_loader()
    try:
        result = loader.extract_bytes(content=content, filename=file.filename, suffix=suffix)
    except Exception as exc:
        return _error_response(
            request=request,
            status_code=500,
            errors=[_api_error(
                ErrorCode.EXTRACTION_FAILED,
                "Document extraction failed.",
                detail=str(exc),
            )],
        )

    # --- build response ---
    doc_info = DocumentInfo(
        filename=result.filename,
        format=result.metadata.get("format", suffix.lstrip(".")),
        type=result.metadata.get("type", "Unknown"),
        page_count=result.page_count,
        file_size_bytes=result.file_size_bytes,
    )

    # Handle output_format: markitdown always produces markdown;
    # if user requests plain text we strip basic md markers.
    text = result.markdown
    if output_format == "text":
        text = _strip_markdown(text)

    content_info = ContentInfo(
        format=output_format,
        text=text,
        length=len(text),
    )

    data = ExtractionData(document=doc_info, content=content_info)

    if store:
        doc_id = uuid.uuid4().hex
        _doc_store[doc_id] = data

    elapsed = (time.perf_counter() - t0) * 1000
    return ApiResponse.success(
        data=data.model_dump(),
        request_id=_request_id(request),
        processing_time_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Retrieve stored document
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{doc_id}",
    response_model=ApiResponse,
    summary="Retrieve a stored document",
)
async def get_document(request: Request, doc_id: str):
    data = _doc_store.get(doc_id)
    if data is None:
        return _error_response(
            request=request,
            status_code=404,
            errors=[_api_error(ErrorCode.NOT_FOUND, f"Document '{doc_id}' not found.")],
        )
    return ApiResponse.success(data=data.model_dump(), request_id=_request_id(request))


# ---------------------------------------------------------------------------
# Lightweight markdown → plain-text stripper
# ---------------------------------------------------------------------------

import re as _re

def _strip_markdown(text: str) -> str:
    # Remove headings, bold/italic markers, link syntax, code fences, blockquotes, horizontal rules
    text = _re.sub(r"(?m)^#{1,6}\s+", "", text)           # headings
    text = _re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text) # bold / italic
    text = _re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)   # bold / italic (underscore)
    text = _re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text) # links
    text = _re.sub(r"`{1,3}[^`]*`{1,3}", "", text)        # inline code
    text = _re.sub(r"(?m)^>\s?", "", text)                 # blockquotes
    text = _re.sub(r"(?m)^[-*_]{3,}\s*$", "", text)       # horizontal rules
    text = _re.sub(r"\n{3,}", "\n\n", text)                # collapse blank lines
    return text.strip()
