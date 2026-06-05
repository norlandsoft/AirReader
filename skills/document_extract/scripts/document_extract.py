#!/usr/bin/env python3
"""document_extract — AirReader PDF 文档内容提取 CLI 工具

通过 AirReader REST API 将 PDF 文档提取为 Markdown。
图片以原始分辨率保存为独立 PNG 文件。
服务端返回 zip 包（Markdown + 图片 + 元数据），客户端解包即可。
纯 Python 标准库实现，零第三方依赖。要求 Python 3.8+。
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:9103"
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
    向 AirReader API 发送请求。

    返回值：
    - 成功：{"status": "success", "_is_zip": True, "_zip_data": bytes}
    - 错误：{"status": "failure", "errors": [...]}
    """
    url = f"{base_url.rstrip('/')}/api/v1/{endpoint.lstrip('/')}"

    body = None
    headers = {}

    if files:
        boundary = f"----AirReader{uuid.uuid4().hex}"
        parts = []

        if form_fields:
            for k, v in form_fields.items():
                parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                    f"{v}\r\n".encode()
                )

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
            content_type = resp.headers.get("Content-Type", "")
            resp_body = resp.read()

            # 成功：服务端返回 zip
            if "application/zip" in content_type:
                return {
                    "status": "success",
                    "_is_zip": True,
                    "_zip_data": resp_body,
                }

            # 其他情况（不应出现）：解析 JSON
            return json.loads(resp_body.decode("utf-8", errors="replace"))

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

def extract_document(base_url, file_path, timeout=DEFAULT_TIMEOUT):
    """
    通过 AirReader API 提取 PDF 文档内容。

    发送 PDF 文件，接收 zip 包（Markdown + 图片 + meta.json）。
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

    result = api_request(
        base_url,
        "convert/file",
        method="POST",
        files=[(file_path.name, file_bytes, "application/pdf")],
        timeout=timeout,
    )

    if isinstance(result, dict) and result.get("_is_zip"):
        result["filename"] = file_path.name

    return result


# ── Zip 解包 ──────────────────────────────────────────────────────────

def unpack_zip(zip_data, output_path):
    """
    将服务端返回的 zip 包解压到输出文件所在目录，
    并将文件名统一重命名为用户指定的输出文件名。

    例如 zip 中为 upload_xxx.md + upload_xxx_images/，
    重命名为 Project.md + Project_images/，使 Markdown 中的相对图片引用保持有效。

    返回 (meta_dict, image_count, images_dir_path)
    """
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    output_base = os.path.splitext(os.path.basename(output_path))[0]

    meta = None
    md_source = None
    images_dir_source = None
    image_count = 0

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                # 记录图片目录路径
                if name.rstrip("/").endswith("_images"):
                    images_dir_source = os.path.join(output_dir, name.rstrip("/"))
                continue

            target = os.path.join(output_dir, name)

            # 安全检查：防止路径穿越
            abs_target = os.path.abspath(target)
            if not abs_target.startswith(output_dir + os.sep) and abs_target != output_dir:
                continue

            os.makedirs(os.path.dirname(target), exist_ok=True)
            data = zf.read(name)
            with open(target, "wb") as dst:
                dst.write(data)

            if name == "meta.json":
                meta = json.loads(data)
            elif name.endswith(".md"):
                md_source = target
            elif "_images/" in name:
                image_count += 1
                if images_dir_source is None:
                    # 从图片文件路径推导目录
                    idx = name.find("_images/")
                    if idx > 0:
                        images_dir_source = os.path.join(output_dir, name[:idx + len("_images")])

        # 统一重命名：upload_xxx.md → Project.md, upload_xxx_images/ → Project_images/
        old_images_dir_name = None
        if md_source:
            md_base = os.path.splitext(os.path.basename(md_source))[0]
            if md_base != output_base:
                # 重命名 md 文件
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(md_source, output_path)

                # 重命名图片目录
                old_images_dir = os.path.join(os.path.dirname(md_source), md_base + "_images")
                new_images_dir = os.path.join(output_dir, output_base + "_images")
                if os.path.isdir(old_images_dir) and not os.path.exists(new_images_dir):
                    os.rename(old_images_dir, new_images_dir)
                    images_dir_source = new_images_dir
                    old_images_dir_name = md_base + "_images"

    # 修正 Markdown 中的图片路径
    # ODL 生成的图片引用可能是绝对路径（如 /tmp/odl-xxx/basename_images/file.png），
    # 替换为相对路径（如 Project_images/file.png）
    if image_count > 0 and os.path.exists(output_path):
        new_images_rel = output_base + "_images"
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配 Markdown 图片语法中的路径，替换为相对路径
        # 形如 ![alt](any/path/xxx_images/imageFile1.png) → ![alt](Project_images/imageFile1.png)
        def _fix_path(m):
            alt = m.group(1)
            path = m.group(2)
            filename = os.path.basename(path)
            return f"![{alt}]({new_images_rel}/{filename})"

        new_content = re.sub(r'!\[([^\]]*)\]\(([^)]*_images/[^)]*)\)', _fix_path, content)

        if new_content != content:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(new_content)

    return meta, image_count, images_dir_source


# ── 输出格式化 ────────────────────────────────────────────────────────

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def format_error(result, elapsed=0):
    """格式化错误输出到 stderr，返回退出码"""
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


def print_success(meta, image_count, filename, elapsed):
    """提取摘要输出到 stderr"""
    print(f"✅ 提取成功", file=sys.stderr)
    print(f"📄 文件: {meta.get('filename', filename) if meta else filename}", file=sys.stderr)
    if meta:
        print(f"📐 大小: {format_size(meta.get('file_size_bytes', 0))}", file=sys.stderr)
    if image_count > 0:
        print(f"🖼 提取图片: {image_count} 张", file=sys.stderr)
    if meta:
        proc_time = meta.get("processing_time", 0)
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

    result = extract_document(
        base_url=base_url,
        file_path=args.input_file,
        timeout=args.timeout,
    )

    elapsed = time.time() - t0

    if result.get("status") != "success":
        return format_error(result, elapsed)

    # 解包 zip 到输出目录
    meta, image_count, images_dir = unpack_zip(result["_zip_data"], args.output)
    print_success(meta, image_count, result.get("filename", "?"), elapsed)
    print(f"💾 已保存: {args.output}", file=sys.stderr)

    if image_count > 0 and images_dir:
        print(f"📁 图片目录: {images_dir}", file=sys.stderr)

    return 0


# ── CLI ────────────────────────────────────────────────────────────────

def parse_args(argv=None):
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="document_extract — AirReader PDF 文档内容提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python3 document_extract.py report.pdf -o report.md\n"
               "  python3 document_extract.py slides.pdf --url http://192.168.1.100:9103 -o slides.md",
    )

    parser.add_argument("input_file", help="PDF 文件路径")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"AirReader 服务地址（默认 {DEFAULT_URL}）")
    parser.add_argument("--output", "-o", required=True, help="输出文件路径")
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
