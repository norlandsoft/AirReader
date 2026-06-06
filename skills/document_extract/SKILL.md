---
name: document_extract
description: Use when converting PDF files to Markdown with images via the AirParser service.
source: project
---

# document_extract — PDF 文档提取

将 PDF 文档提取为 Markdown + 原始分辨率图片。

- 图片按原文位置穿插，非末尾堆叠
- 表格转为 Markdown 表格格式
- 自动过滤页眉页脚（文字和图片）
- 图片 smask 合成到白色背景，无黑色透明区域

**前置条件：** AirParser 服务运行中（默认 `http://localhost:9103`）。

**支持格式：** PDF（≤ 50 MB）。

---

## 参数

| 参数 | 必选 | 默认值 | 说明 |
|------|------|--------|------|
| `input_file` | 是 | — | PDF 文件路径 |
| `--output, -o` | 是 | — | 输出 Markdown 文件路径 |
| `--url` | 否 | `http://localhost:9103` | AirParser 服务地址 |
| `--timeout` | 否 | `300` | HTTP 请求超时（秒） |

---

## 使用示例

```bash
# 基本用法
python3 scripts/document_extract.py report.pdf -o report.md
# 输出: report.md + report_images/

# 指定服务地址
python3 scripts/document_extract.py slides.pdf \
  --url http://192.168.1.100:9103 -o slides.md
```

**输出结构：**
```
report.md                    # Markdown
report_images/               # 图片
    img_0.jpeg
    img_1.png
```

---

## API 参考

### Health Check

```
GET /api/v1/health
→ {"status": "healthy", "version": "3.0.0"}
```

### 转换

```
POST /api/v1/convert/file
Content-Type: multipart/form-data
字段名: files
→ application/zip 流
```

**所有响应（成功和错误）均为 `application/zip`，HTTP 200。** 错误信息在 zip 内 `meta.json` 中。

### meta.json 格式

**成功：**
```json
{
  "filename": "report.pdf",
  "file_size_bytes": 1048576,
  "processing_time": 1.23,
  "status": "success"
}
```

**失败：**
```json
{
  "filename": "report.pdf",
  "file_size_bytes": 0,
  "processing_time": 0.01,
  "status": "failure",
  "errors": [{"code": "ERROR_CODE", "message": "描述"}]
}
```

### 错误码

| 错误码 | 触发条件 |
|--------|----------|
| `INVALID_REQUEST` | 缺少文件名或请求格式错误 |
| `UNSUPPORTED_FORMAT` | 非 PDF 文件 |
| `EMPTY_FILE` | 上传文件为空 |
| `FILE_TOO_LARGE` | 超过 50 MB |
| `EXTRACTION_FAILED` | PDF 解析失败 |
