"""FastAPI application entry point."""
import json
import logging
import zipfile
from io import BytesIO

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from app.router.convert import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="AirParser", version="3.0.0")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return an error zip for validation failures (missing/invalid upload)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "filename": "error.pdf",
            "file_size_bytes": 0,
            "processing_time": 0,
            "status": "failure",
            "errors": [{"code": "INVALID_REQUEST", "message": "缺少文件名或请求格式错误"}],
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="error.zip"'},
    )
