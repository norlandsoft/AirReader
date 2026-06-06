---
name: document_extract
description: 将 PDF 文件通过 AirParser 服务提取为 Markdown，图片以原始分辨率保存。基于 PyMuPDF + pdfplumber。
source: project
---

# document_extract — PDF 内容提取

## 概述

调用 AirParser 服务，将 PDF 文档内容提取为 Markdown 格式。底层使用 PyMuPDF 提取文字和原始分辨率图片，pdfplumber 提取表格。

- PDF 中的图片以原始分辨率保存（不压缩、不 base64 嵌入）
- 服务端将 Markdown + 图片打包为 zip 流式返回
- 客户端解包即可使用，图片相对路径天然有效

**前置条件：** AirParser 服务运行中（默认 `http://localhost:9103`）。

**支持的格式：** 仅 PDF 文件（≤ 50 MB）。

---

## 参数

| 参数 | 必选 | 默认值 | 说明 |
|------|------|--------|------|
| `input_file` | 是 | — | PDF 文件路径 |
| `--output, -o` | 是 | — | 输出 Markdown 文件路径 |
| `--url` | 否 | `http://localhost:9103` | AirParser 服务地址 |
| `--timeout` | 否 | `300` | HTTP 请求超时秒数 |

---

## 使用示例

```bash
# 提取 PDF 为 Markdown + 图片
python3 scripts/document_extract.py report.pdf -o report.md
# 输出: report.md + report_images/img_0.png, report_images/img_1.jpeg, ...

# 指定服务地址
python3 scripts/document_extract.py slides.pdf --url http://192.168.1.100:9103 -o slides.md
```

---

## 工作流程

1. 脚本将 PDF 文件上传到 AirParser 服务 `POST /api/v1/convert/file`
2. 服务端使用 PyMuPDF 提取文字和原始分辨率图片，pdfplumber 提取表格
3. 服务端将 `Markdown 文件` + `图片目录` + `meta.json` 流式打包为 zip 返回
4. 脚本接收 zip 包，解压到输出文件所在目录

**输出目录结构：**
```
report.md                    # Markdown（图片引用为 report_images/img_0.png）
report_images/               # 原始分辨率图片
    img_0.png
    img_1.jpeg
```

---

## API 响应

| 场景 | HTTP 状态 | Content-Type | 说明 |
|------|----------|--------------|------|
| 成功 | 200 | `application/zip` | 流式 zip 包 |
| 错误 | 200 | `application/zip` | zip 内 meta.json 含 failure 状态 |
