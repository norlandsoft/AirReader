"""AirFileReader — FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models import ApiError, ApiResponse, ErrorCode
from app.routers.document import router as document_router

app = FastAPI(
    title="AirFileReader",
    description="OpenDataLoader service — extract document content as Markdown",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Exception handlers — all return the unified ApiResponse envelope
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    # If the router already packed an ApiResponse dict into detail, unwrap it
    if isinstance(detail, dict) and detail.get("status") == "error":
        return JSONResponse(status_code=exc.status_code, content=detail)
    # Otherwise wrap the plain detail in our envelope
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.error(
            errors=[ApiError(code=ErrorCode.INTERNAL_ERROR, message=str(detail))],
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        loc = " → ".join(str(p) for p in err["loc"])
        messages.append(f"{loc}: {err['msg']}")
    return JSONResponse(
        status_code=422,
        content=ApiResponse.error(
            errors=[ApiError(
                code=ErrorCode.INVALID_REQUEST,
                message="Request validation failed.",
                detail="; ".join(messages),
            )],
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def _catchall_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(
            errors=[ApiError(
                code=ErrorCode.INTERNAL_ERROR,
                message="An unexpected error occurred.",
                detail=str(exc),
            )],
        ).model_dump(),
    )


@app.get("/")
async def root():
    return {
        "service": "AirFileReader",
        "version": "1.0.0",
        "docs": "/docs",
    }
