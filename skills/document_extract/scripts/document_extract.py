#!/usr/bin/env python3
"""document_extract — AirFileReader 文档内容提取 CLI 工具

通过 AirFileReader REST API 将文档（PDF/Word/PPT/Excel/HTML/TXT 等）
提取为 Markdown 或纯文本。纯 Python 标准库实现，零第三方依赖。
要求 Python 3.8+。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:9103"
DEFAULT_OUTPUT_FORMAT = "markdown"
DEFAULT_TIMEOUT = 300

SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv", ".html", ".htm",
    ".txt", ".md", ".jpg", ".jpeg", ".png",
})


# ── HTTP ──────────────────────────────────────────────────────────────

class _NoProxyHandler(urllib.request.ProxyHandler):
    """Proxy handler that bypasses all proxies."""
    def __init__(self):
        super().__init__({})

    def proxy_open(self, req, proxy, type):
        return None


def _build_opener(timeout):
    """Build a urllib opener with proxy bypass."""
    return urllib.request.build_opener(
        _NoProxyHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
    )


def api_request(base_url, endpoint, method="GET", files=None, params=None, timeout=DEFAULT_TIMEOUT):
    """Send request to AirFileReader API. Returns parsed JSON."""
    url = f"{base_url.rstrip('/')}/api/v1/{endpoint.lstrip('/')}"

    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items() if v is not None)
        url = f"{url}?{qs}"

    body = None
    headers = {}

    if files:
        boundary = f"----FileReaderBoundary{uuid.uuid4().hex}"
        parts = []
        for fname, fbytes, fmime in files:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                f"Content-Type: {fmime}\r\n\r\n".encode()
                + fbytes
                + b"\r\n"
            )
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif method == "POST":
        body = b""
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = _build_opener(timeout)

    try:
        with opener.open(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            return json.loads(resp_body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            return parsed
        except json.JSONDecodeError:
            return {"status": "error", "errors": [{"code": "HTTP_ERROR", "message": f"HTTP {e.code}: {body[:500]}"}]}
    except urllib.error.URLError as e:
        return {"status": "error", "errors": [{"code": "CONNECTION_ERROR", "message": f"连接失败: {e.reason}"}]}
    except Exception as e:
        return {"status": "error", "errors": [{"code": "UNKNOWN_ERROR", "message": str(e)}]}


def health_check(base_url, timeout):
    """Check if AirFileReader is reachable."""
    result = api_request(base_url, "health", timeout=timeout)
    if isinstance(result, dict) and result.get("status") == "success":
        return True
    return False


# ── 文档提取 ──────────────────────────────────────────────────────────

def extract_document(base_url, file_path, output_format="markdown", timeout=DEFAULT_TIMEOUT):
    """Extract document content via AirFileReader API. Returns result dict."""
    file_path = Path(file_path)
    if not file_path.exists():
        return {"status": "error", "errors": [{"code": "FILE_NOT_FOUND", "message": f"文件不存在: {file_path}"}]}

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "errors": [{"code": "UNSUPPORTED_FORMAT", "message": f"不支持的文件类型: {suffix}"}],
        }

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    if not file_bytes:
        return {"status": "error", "errors": [{"code": "EMPTY_FILE", "message": "文件为空"}]}

    mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".html": "text/html",
        ".htm": "text/html",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    mime = mime_map.get(suffix, "application/octet-stream")

    params = {"output_format": output_format} if output_format != "markdown" else {}

    return api_request(
        base_url,
        "documents/extract",
        method="POST",
        files=[(file_path.name, file_bytes, mime)],
        params=params if params else None,
        timeout=timeout,
    )


# ── 输出格式化 ────────────────────────────────────────────────────────

def format_error(result, file_path="", elapsed=0):
    """Format API error for stderr output. Returns exit code."""
    errors = result.get("errors", [])
    if not errors:
        print("❌ 未知错误", file=sys.stderr)
        return 1

    for err in errors:
        code = err.get("code", "UNKNOWN")
        message = err.get("message", "未知错误")
        detail = err.get("detail", "")
        print(f"❌ [{code}] {message}", file=sys.stderr)
        if detail:
            print(f"   详情: {detail}", file=sys.stderr)

    if elapsed:
        print(f"⏱ 耗时: {elapsed:.1f}s", file=sys.stderr)
    return 1


def print_success(result, elapsed):
    """Print extraction success info to stderr and content to stdout."""
    data = result.get("data", {})
    doc = data.get("document", {})
    content = data.get("content", {})
    meta = result.get("metadata", {})

    # Summary to stderr
    print(f"✅ 提取成功", file=sys.stderr)
    print(f"📄 文件: {doc.get('filename', '?')}", file=sys.stderr)
    print(f"📐 类型: {doc.get('type', '?')}  |  格式: {doc.get('format', '?')}"
          f"  |  {'页数: ' + str(doc['page_count']) if doc.get('page_count') else '大小: ' + format_size(doc.get('file_size_bytes', 0))}",
          file=sys.stderr)
    print(f"📝 内容长度: {content.get('length', 0)} 字符  |  "
          f"格式: {content.get('format', 'markdown')}", file=sys.stderr)
    print(f"⏱ 处理耗时: {meta.get('processing_time_ms', 0):.0f} ms  |  "
          f"总耗时: {elapsed:.1f}s", file=sys.stderr)
    print(f"🔑 Request ID: {meta.get('request_id', '?')}", file=sys.stderr)
    print("─" * 50, file=sys.stderr)


def format_size(size_bytes):
    """Format bytes to human-readable size."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


# ── 主流程 ────────────────────────────────────────────────────────────

def run(args):
    """Main run function. Returns exit code."""
    t0 = time.time()
    base_url = args.url.rstrip("/")

    # ── 健康检查 ──
    if not health_check(base_url, timeout=args.timeout):
        print(f"❌ AirFileReader 服务不可达 ({base_url})", file=sys.stderr)
        return 1

    # ── 提取文档 ──
    result = extract_document(
        base_url=base_url,
        file_path=args.input_file,
        output_format=args.output_format,
        timeout=args.timeout,
    )

    elapsed = time.time() - t0

    if result.get("status") != "success":
        return format_error(result, args.input_file, elapsed)

    # ── 输出内容 ──
    content_text = result["data"]["content"]["text"]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content_text)
        print_success(result, elapsed)
        print(f"💾 已保存: {args.output}", file=sys.stderr)
    else:
        # Print summary to stderr, content to stdout for piping
        print_success(result, elapsed)
        sys.stdout.write(content_text)

    return 0


# ── CLI ─────────────────────────────────────────────────────────────────

def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="document_extract — AirFileReader 文档内容提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python3 document_extract.py report.pdf -o report.md\n"
               "  python3 document_extract.py document.docx --output-format text\n"
               "  python3 document_extract.py notes.txt\n"
               "  python3 document_extract.py slides.pptx --url http://192.168.1.100:9103",
    )

    parser.add_argument("input_file", help="输入文件路径（PDF/DOCX/PPTX/XLSX/HTML/TXT/MD/CSV/图片等）")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"AirFileReader 服务地址（默认 {DEFAULT_URL}）")
    parser.add_argument("--output", "-o", help="输出文件路径（不指定则打印到标准输出）")
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=["markdown", "text"],
                        help=f"输出格式（默认 {DEFAULT_OUTPUT_FORMAT}）")
    parser.add_argument("--request-id", help="自定义请求追踪 ID")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"HTTP 请求超时秒数（默认 {DEFAULT_TIMEOUT}）")

    args = parser.parse_args(argv)

    if not os.path.isfile(args.input_file):
        parser.error(f"输入文件不存在: {args.input_file}")

    return args


def main():
    args = parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        print("\n⚠ 已中断", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
