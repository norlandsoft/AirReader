---
name: document_extract
description: 将 PDF 文件通过 AirFileReader 的 OpenDataLoader 服务提取为 Markdown 或纯文本。基于 opendataloader-pdf-core 库，Docling 风格 API。
source: project
---

# document_extract — PDF 内容提取

## 概述

调用 AirFileReader 的 OpenDataLoader 服务，将 PDF 文档内容提取为 Markdown 或纯文本格式。底层使用 opendataloader-pdf-core 库进行进程内 JVM 解析。

**主要特性：**
- 基于 opendataloader-pdf-core 库的高质量 PDF 提取
- Docling 风格 API（POST /v1alpha/convert/file）
- 输出格式可选：Markdown（默认）或纯文本
- 支持自定义服务地址
- 返回处理耗时和文件元信息

**前置条件：** AirFileReader 服务运行中（默认 `http://localhost:9103`）。

**支持的格式：** 仅 PDF 文件。

---

## 快速参考

| 项目 | 值 |
|------|-----|
| 脚本路径 | `scripts/document_extract.py`（相对于 skill 目录） |
| 运行方式 | `python3 scripts/document_extract.py <input_file.pdf> [选项]` |
| 输出格式 | Markdown（默认）、纯文本 |
| API 端点 | `POST /v1alpha/convert/file` |

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
| `--output, -o` | 标准输出 | 输出文件路径 |
| `--output-format` | `markdown` | 输出格式：`markdown` 或 `text` |
| `--timeout` | `300` | HTTP 请求超时秒数 |

---

## 使用示例

```bash
# 提取 PDF 为 Markdown
python3 scripts/document_extract.py report.pdf -o report.md

# 提取为纯文本
python3 scripts/document_extract.py document.pdf --output-format text

# 指定服务地址
python3 scripts/document_extract.py slides.pdf --url http://192.168.1.100:9103
```

---

## 注意事项

- 仅支持 PDF 格式文件
- 文件大小限制 50 MB
- 服务端自动记录处理耗时（毫秒级）
