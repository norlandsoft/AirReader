---
name: document_extract
description: 将 PDF 文件通过 AirReader 的 OpenDataLoader 服务提取为 Markdown，图片以原始分辨率保存为独立 PNG 文件。基于 opendataloader-pdf-core 库。
source: project
---

# document_extract — PDF 内容提取

## 概述

调用 AirReader 的 OpenDataLoader 服务，将 PDF 文档内容提取为 Markdown 格式。底层使用 opendataloader-pdf-core 库进行进程内 JVM 解析。

- PDF 中的图片以原始分辨率保存为独立 PNG 文件（不压缩、不 base64 嵌入）
- 服务端将 Markdown + 图片打包为 zip 流式返回
- 客户端解包即可使用，图片相对路径天然有效

**前置条件：** AirReader 服务运行中（默认 `http://localhost:9103`）。

**支持的格式：** 仅 PDF 文件（≤ 50 MB）。

---

## 参数

| 参数 | 必选 | 默认值 | 说明 |
|------|------|--------|------|
| `input_file` | 是 | — | PDF 文件路径 |
| `--output, -o` | 是 | — | 输出 Markdown 文件路径 |
| `--url` | 否 | `http://localhost:9103` | AirReader 服务地址 |
| `--timeout` | 否 | `300` | HTTP 请求超时秒数 |

---

## 使用示例

```bash
# 提取 PDF 为 Markdown + 图片
python3 scripts/document_extract.py report.pdf -o report.md
# 输出: report.md + report_images/image_001.png, report_images/image_002.png, ...

# 指定服务地址
python3 scripts/document_extract.py slides.pdf --url http://192.168.1.100:9103 -o slides.md
```

---

## 工作流程

1. 脚本将 PDF 文件上传到 AirReader 服务 `POST /api/v1/convert/file`
2. 服务端使用 OpenDataLoader 提取 PDF 内容为 Markdown，同时提取图片为原始 PNG 文件
3. 服务端将 `Markdown 文件` + `图片目录` + `meta.json` 流式打包为 zip 返回
4. 脚本接收 zip 包，解压到输出文件所在目录

**输出目录结构：**
```
report.md                    # Markdown（图片引用为 report_images/image_001.png）
report_images/               # 原始 PNG 图片
    image_001.png
    image_002.png
```

---

## API 响应

| 场景 | HTTP 状态 | Content-Type | 说明 |
|------|----------|--------------|------|
| 成功 | 200 | `application/zip` | 流式 zip 包 |
| 错误 | 4xx / 5xx | `application/json` | `{"status":"failure","errors":[...]}` |
