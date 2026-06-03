"""Pydantic models for the AirFileReader API.

Response design follows the docling / enterprise document API pattern:
- Unified envelope with status, data, errors, metadata
- Structured error objects with machine-readable codes
- Request ID and processing-time tracking
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class ErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ApiError(BaseModel):
    code: ErrorCode = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error summary.")
    detail: Optional[str] = Field(None, description="Additional diagnostic detail.")


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------

class DocumentInfo(BaseModel):
    filename: str = Field(..., description="Original filename.")
    format: str = Field(..., description="File extension without dot, e.g. 'pdf'.")
    type: str = Field(..., description="Human-readable document type, e.g. 'PDF'.")
    page_count: int = Field(0, description="Number of pages (PDF only).")
    file_size_bytes: int = Field(..., description="Uploaded file size in bytes.")


# ---------------------------------------------------------------------------
# Extracted content
# ---------------------------------------------------------------------------

class ContentInfo(BaseModel):
    format: str = Field("markdown", description="Output format: 'markdown' or 'text'.")
    text: str = Field(..., description="The extracted document content.")
    length: int = Field(..., description="Character count of the extracted text.")


# ---------------------------------------------------------------------------
# Response data
# ---------------------------------------------------------------------------

class ExtractionData(BaseModel):
    document: DocumentInfo
    content: ContentInfo


# ---------------------------------------------------------------------------
# Response metadata
# ---------------------------------------------------------------------------

class ResponseMetadata(BaseModel):
    request_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique identifier for this request.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp.",
    )
    api_version: str = Field("1.0.0", description="API version.")
    processing_time_ms: float = Field(0.0, description="Server-side processing time in milliseconds.")


# ---------------------------------------------------------------------------
# Unified response envelope
# ---------------------------------------------------------------------------

class ApiResponse(BaseModel):
    """Top-level envelope for every API response."""

    status: str = Field("success", description="'success' or 'error'.")
    data: Optional[Any] = Field(None, description="Response payload (null on error).")
    errors: list[ApiError] = Field(default_factory=list, description="Error list (empty on success).")
    metadata: ResponseMetadata = Field(
        default_factory=ResponseMetadata,
        description="Request-scoped metadata.",
    )

    @classmethod
    def success(cls, data: Any, request_id: str = "", processing_time_ms: float = 0.0) -> "ApiResponse":
        meta = ResponseMetadata(
            request_id=request_id or uuid.uuid4().hex,
            processing_time_ms=round(processing_time_ms, 2),
        )
        return cls(status="success", data=data, errors=[], metadata=meta)

    @classmethod
    def error(
        cls,
        errors: list[ApiError],
        request_id: str = "",
        processing_time_ms: float = 0.0,
    ) -> "ApiResponse":
        meta = ResponseMetadata(
            request_id=request_id or uuid.uuid4().hex,
            processing_time_ms=round(processing_time_ms, 2),
        )
        return cls(status="error", data=None, errors=errors, metadata=meta)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthData(BaseModel):
    service: str = "AirFileReader"
    version: str = "1.0.0"
    status: str = "healthy"
