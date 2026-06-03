#!/usr/bin/env python3
"""document_extract — AirReader 文档内容提取 CLI 工具

通过 AirReader REST API 将 PDF 文档提取为 Markdown 或纯文本。
纯 Python 标准库实现，零第三方依赖。要求 Python 3.8+。
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
DEFAULT_OUTPUT_FORMAT = "md"
DEFAULT_TIMEOUT = 300


# ── HTTP ──────────────────────────────────────────────────────────────

class _NoProxyHandler(urllib.request.ProxyHandler):
    """绕过所有代理的 Handler"""
    def __init__(self):
        super().__init__({})

    def proxy_open(self, req, proxy, type):
        return None


def _build_opener():
    """构建绕过代理的 urllib opener"""
    return urllib.request.build_opener(
        _NoProxyHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
    )


def api_request(base_url, endpoint, method="GET", files=None, form_fields=None, timeout=DEFAULT_TIMEOUT):
    """
    向 AirReader API 发送请求，返回解析后的 JSON。

    files: [(filename, bytes, mime)] 文件列表
    form_fields: {key: value} 额外表单字段
    """
    url = f"{base_url.rstrip('/')}/api/v1/{endpoint.lstrip('/')}"

    body = None
    headers = {}

    if files:
        # 构建 multipart/form-data 请求体
        boundary = f"----AirReader{uuid.uuid4().hex}"
        parts = []

        # 添加表单字段
        if form_fields:
            for k, v in form_fields.items():
                parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                    f"{v}\r\n".encode()
                )

        # 添加文件（参数名 files，对齐 Docling 风格）
        for fname, fbytes, fmime in files:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{fname}"\r\n'
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
    opener = _build_opener()

    try:
        with opener.open(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            return json.loads(resp_body)
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(resp_body)
        except json.JSONDecodeError:
            return {"status": "failure", "errors": [{"code": "HTTP_ERROR", "message": f"HTTP {e.code}: {resp_body[:500]}"}]}
    except urllib.error.URLError as e:
        return {"status": "failure", "errors": [{"code": "CONNECTION_ERROR", "message": f"连接失败: {e.reason}"}]}
    except Exception as e:
        return {"status": "failure", "errors": [{"code": "UNKNOWN_ERROR", "message": str(e)}]}


def health_check(base_url, timeout):
    """检查 AirReader 服务是否可达"""
    try:
        result = api_request(base_url, "health", timeout=timeout)
        return isinstance(result, dict) and result.get("status") == "healthy"
    except Exception:
        return False


# ── 文档提取 ──────────────────────────────────────────────────────────

def extract_document(base_url, file_path, output_format="md", timeout=DEFAULT_TIMEOUT):
    """
    通过 AirReader API 提取 PDF 文档内容。

    对齐 Docling 风格的 POST /api/v1/convert/file 端点：
    - files: PDF 文件（multipart form）
    - to_formats: 输出格式（md 或 text）
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return {"status": "failure", "errors": [{"code": "FILE_NOT_FOUND", "message": f"文件不存在: {file_path}"}]}

    suffix = file_path.suffix.lower()
    if suffix != ".pdf":
        return {"status": "failure", "errors": [{"code": "UNSUPPORTED_FORMAT", "message": f"仅支持 PDF 文件，收到: {suffix}"}]}

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    if not file_bytes:
        return {"status": "failure", "errors": [{"code": "EMPTY_FILE", "message": "文件为空"}]}

    form_fields = {}
    if output_format and output_format != "md":
        form_fields["to_formats"] = output_format

    return api_request(
        base_url,
        "convert/file",
        method="POST",
        files=[(file_path.name, file_bytes, "application/pdf")],
        form_fields=form_fields if form_fields else None,
        timeout=timeout,
    )


# ── 输出格式化 ────────────────────────────────────────────────────────

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def format_error(result, elapsed=0):
    """格式化 API 错误输出到 stderr，返回退出码"""
    errors = result.get("errors", [])
    if not errors:
        print("❌ 未知错误", file=sys.stderr)
        return 1

    for err in errors:
        code = err.get("code", "UNKNOWN")
        message = err.get("message", "未知错误")
        print(f"❌ [{code}] {message}", file=sys.stderr)

    if elapsed:
        print(f"⏱ 耗时: {elapsed:.1f}s", file=sys.stderr)
    return 1


def print_success(result, elapsed):
    """将提取摘要输出到 stderr"""
    doc = result.get("document", {})

    print(f"✅ 提取成功", file=sys.stderr)
    print(f"📄 文件: {doc.get('filename', '?')}", file=sys.stderr)
    print(f"📐 大小: {format_size(doc.get('file_size_bytes', 0))}", file=sys.stderr)

    md_len = len(doc.get("md_content", "")) if doc.get("md_content") else 0
    text_len = len(doc.get("text_content", "")) if doc.get("text_content") else 0
    print(f"📝 内容长度: {max(md_len, text_len)} 字符", file=sys.stderr)

    proc_time = result.get("processing_time", 0)
    print(f"⏱ 服务处理: {proc_time:.2f}s  |  总耗时: {elapsed:.1f}s", file=sys.stderr)
    print("─" * 50, file=sys.stderr)


# ── 主流程 ────────────────────────────────────────────────────────────

def run(args):
    """主流程，返回退出码"""
    t0 = time.time()
    base_url = args.url.rstrip("/")

    # 健康检查
    if not health_check(base_url, timeout=args.timeout):
        print(f"❌ AirReader 服务不可达 ({base_url})", file=sys.stderr)
        return 1

    # 提取文档
    result = extract_document(
        base_url=base_url,
        file_path=args.input_file,
        output_format=args.output_format,
        timeout=args.timeout,
    )

    elapsed = time.time() - t0

    if result.get("status") != "success":
        return format_error(result, elapsed)

    # 获取内容：优先 md_content，如果请求了 text 则取 text_content
    doc = result.get("document", {})
    if args.output_format == "text" and doc.get("text_content"):
        content_text = doc["text_content"]
    else:
        content_text = doc.get("md_content", "")

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content_text)
        print_success(result, elapsed)
        print(f"💾 已保存: {args.output}", file=sys.stderr)
    else:
        print_success(result, elapsed)
        sys.stdout.write(content_text)

    return 0


# ── CLI ────────────────────────────────────────────────────────────────

def parse_args(argv=None):
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="document_extract — AirReader PDF 文档内容提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python3 document_extract.py report.pdf -o report.md\n"
               "  python3 document_extract.py document.pdf --output-format text\n"
               "  python3 document_extract.py slides.pdf --url http://192.168.1.100:9103",
    )

    parser.add_argument("input_file", help="PDF 文件路径")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"AirReader 服务地址（默认 {DEFAULT_URL}）")
    parser.add_argument("--output", "-o", help="输出文件路径（不指定则打印到标准输出）")
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=["md", "text"],
                        help=f"输出格式（默认 {DEFAULT_OUTPUT_FORMAT}）")
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
