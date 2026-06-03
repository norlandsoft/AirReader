---
name: document_extract
description: 将 PDF 文件通过 AirReader 的 OpenDataLoader 服务提取为 Markdown 或纯文本，支持图片提取。基于 opendataloader-pdf-core 库，Docling 风格 API。
source: project
---

# document_extract — PDF 内容提取

## 概述

调用 AirReader 的 OpenDataLoader 服务，将 PDF 文档内容提取为 Markdown 或纯文本格式。底层使用 opendataloader-pdf-core 库进行进程内 JVM 解析。支持将 PDF 中的图片提取为独立 PNG 文件保存到本地。

**主要特性：**
- 基于 opendataloader-pdf-core 库的高质量 PDF 提取
- Docling 风格 API（POST /api/v1/convert/file）
- 输出格式可选：Markdown（默认）或纯文本
- 图片提取：将 PDF 中的图片保存为独立 PNG 文件，Markdown 中保留本地路径引用
- 支持自定义服务地址
- 返回处理耗时和文件元信息

**前置条件：** AirReader 服务运行中（默认 `http://localhost:9103`）。

**支持的格式：** 仅 PDF 文件。

---

## 快速参考

| 项目 | 值 |
|------|-----|
| 脚本路径 | `scripts/document_extract.py`（相对于 skill 目录） |
| 运行方式 | `python3 scripts/document_extract.py <input_file.pdf> [选项]` |
| 输出格式 | Markdown（默认）、纯文本 |
| API 端点 | `POST /api/v1/convert/file` |

---

## 参数说明

### 必选参数

| 参数 | 说明 |
|------|------|
| `input_file` | PDF 文件路径 |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--url` | `http://localhost:9103` | AirReader 服务地址 |
| `--output, -o` | 标准输出 | 输出文件路径 |
| `--output-format` | `md` | 输出格式：`md`（Markdown）或 `text`（纯文本） |
| `--extract-images` | 关闭 | 将 Markdown 中的 base64 图片提取为独立 PNG 文件（需配合 -o） |
| `--timeout` | `300` | HTTP 请求超时秒数 |

---

## 使用示例

```bash
# 提取 PDF 为 Markdown，输出到文件
python3 scripts/document_extract.py report.pdf -o report.md

# 提取为纯文本
python3 scripts/document_extract.py document.pdf --output-format text

# 提取 Markdown 并将图片保存为独立文件
python3 scripts/document_extract.py slides.pdf --extract-images -o slides.md
# 输出: slides.md + images/image_001.png, images/image_002.png, ...

# 指定服务地址
python3 scripts/document_extract.py slides.pdf --url http://192.168.1.100:9103 -o slides.md
```

---

## 图片提取流程

当使用 `--extract-images` 参数时，处理流程如下：

1. 脚本向 AirReader 服务发送请求时附加 `markdown_with_images=true` 参数
2. 服务端使用 OpenDataLoader 提取 PDF 中的图片，转为 base64 嵌入 Markdown
3. 脚本收到 Markdown 后，检测其中的 `data:image/png;base64,...` 数据
4. 将每张图片解码保存到 `images/` 子目录（如 `images/image_001.png`）
5. 将 Markdown 中的 base64 数据替换为本地文件路径（如 `![alt](images/image_001.png)`）

图片提取仅对 `--output-format md`（默认）有效，且必须配合 `-o` 指定输出文件。

---

## 注意事项

- 仅支持 PDF 格式文件
- 文件大小限制 50 MB
- 服务端自动记录处理耗时（秒级）
- 图片提取功能需要 AirReader 服务端支持（启用 markdown_with_images 参数）
