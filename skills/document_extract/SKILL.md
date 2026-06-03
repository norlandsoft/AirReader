---
name: document_extract
description: 将 PDF 文件通过 AirFileReader 的 OpenDataLoader 服务提取为 Markdown 或纯文本。基于 opendataloader-pdf 库，支持自定义服务地址、输出格式、文档暂存。
source: project
---

# document_extract — PDF 内容提取

## 概述

调用 AirFileReader 的 OpenDataLoader 服务，将 PDF 文档内容提取为 Markdown 或纯文本格式。底层使用 [opendataloader-pdf](https://opendataloader.org) 库进行转换，提供高精度的 PDF 文本、表格和标题提取。

**主要特性：**
- 基于 opendataloader-pdf 库的高质量 PDF 提取
- 统一标准化 API 响应：status → data | errors → metadata
- 输出格式可选：Markdown（默认）或纯文本
- 支持自定义服务地址和 X-Request-ID 透传
- 返回 PDF 页码统计
- 失败直接返回错误，无降级策略

**前置条件：** AirFileReader 服务运行中（默认 `http://localhost:9103`）。

**支持的格式：** 仅 PDF 文件。

**零第三方依赖**，仅需 Python 3.8+。

---

## 快速参考

| 项目 | 值 |
|------|-----|
| 脚本路径 | `scripts/document_extract.py`（相对于 skill 目录） |
| 运行方式 | `python3 scripts/document_extract.py <input_file.pdf> [选项]` |
| 输出格式 | Markdown（默认）、纯文本 |
| 支持格式 | PDF only |

---

## 参数说明

### 必选参数

| 参数 | 说明 |
|------|------|
| `input_file` | PDF 文件路径 |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--url` | `http://localhost:9103` | AirFileReader 服务地址 |
| `--output, -o` | 标准输出 | 输出文件路径（不指定则打印到 stdout） |
| `--output-format` | `markdown` | 输出格式：`markdown` 或 `text` |
| `--request-id` | 自动生成 | 自定义请求追踪 ID |
| `--timeout` | `300` | HTTP 请求超时秒数 |

---

## 使用示例

```bash
# 提取 PDF 为 Markdown，输出到文件
python3 scripts/document_extract.py report.pdf -o report.md

# 提取为纯文本
python3 scripts/document_extract.py document.pdf --output-format text

# 指定服务地址
python3 scripts/document_extract.py slides.pdf --url http://192.168.1.100:9103

# 提取并打印到标准输出
python3 scripts/document_extract.py notes.pdf

# 带自定义请求 ID
python3 scripts/document_extract.py data.pdf --request-id batch-job-001
```

---

## 输出说明

成功时输出文件或标准输出为提取后的 Markdown/纯文本内容。脚本返回码 0。

失败时输出错误信息到 stderr，脚本返回码 1。错误信息包含：
- 错误码（如 `EXTRACTION_FAILED`、`UNSUPPORTED_FORMAT`、`EMPTY_FILE` 等）
- 错误描述
- 详细诊断信息

---

## 注意事项

- 仅支持 PDF 格式文件
- 文件大小限制 50 MB
- 服务端自动记录处理耗时（毫秒级）
- 使用 opendataloader-pdf 库进行提取，无降级策略
