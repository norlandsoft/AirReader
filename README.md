# AirReader

PDF 文档内容读取服务 — 基于 OpenDataLoader 将 PDF 转换为 Markdown，通过 Docling 风格的 REST API 对外提供服务。

## 功能

- **PDF 提取**：使用 OpenDataLoader 进程内 JVM 解析，将 PDF 内容转换为 Markdown 或纯文本
- **Docling 风格 API**：对齐 Docling-serve v0.3.0 的端点路径和响应结构，便于与 Docling 生态集成
- **容器化部署**：提供 Dockerfile 和 docker-compose，一键构建和部署

## 快速开始

### Docker 部署

```bash
# 使用 docker compose（推荐）
docker compose up -d

# 或手动构建
docker build -t air-reader:latest .
docker run -p 9103:8000 air-reader:latest
```

服务启动后，外部通过 `9103` 端口访问，容器内部监听 `8000` 端口。

### 本地运行

```bash
mvn spring-boot:run
```

## API 接口

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 |
| `POST` | `/api/v1/convert/file` | 上传 PDF 文件，返回 Markdown |

### GET /api/v1/health

健康检查端点。

**请求示例：**

```bash
curl http://localhost:9103/api/v1/health
```

**响应：**

```json
{
  "status": "healthy",
  "version": "2.0.0"
}
```

### POST /api/v1/convert/file

上传 PDF 文件，返回 Markdown 内容。端点路径对齐 Docling-serve 的 `/api/v1/convert/file`。

**请求格式：** `multipart/form-data`

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `files` | File | 是 | — | PDF 文件 |
| `to_formats` | String | 否 | `md` | 输出格式：`md`（Markdown）或 `text`（纯文本） |
| `markdown_with_html` | Boolean | 否 | `false` | Markdown 中是否使用 HTML 标签渲染复杂元素（如表格） |
| `markdown_with_images` | Boolean | 否 | `false` | Markdown 中是否包含图片引用 |
| `keep_line_breaks` | Boolean | 否 | `false` | 是否保留原始换行符 |

**请求示例：**

```bash
# 基本用法：提取 PDF 为 Markdown
curl -X POST http://localhost:9103/api/v1/convert/file \
  -F "files=@document.pdf"

# 提取为纯文本
curl -X POST http://localhost:9103/api/v1/convert/file \
  -F "files=@document.pdf" \
  -F "to_formats=text"

# 启用 HTML 标签（表格渲染更精确）和图片引用
curl -X POST http://localhost:9103/api/v1/convert/file \
  -F "files=@document.pdf" \
  -F "markdown_with_html=true" \
  -F "markdown_with_images=true"

# 组合使用所有参数
curl -X POST http://localhost:9103/api/v1/convert/file \
  -F "files=@report.pdf" \
  -F "to_formats=md" \
  -F "markdown_with_html=true" \
  -F "keep_line_breaks=true"
```

**成功响应（200）：**

```json
{
  "document": {
    "md_content": "# 标题\n\n正文内容...",
    "text_content": null,
    "filename": "document.pdf",
    "page_count": 0,
    "file_size_bytes": 123456
  },
  "status": "success",
  "processing_time": 1.23,
  "errors": []
}
```

当 `to_formats=text` 时，`text_content` 字段会填充去除 Markdown 格式标记后的纯文本内容。

**错误响应示例：**

```json
{
  "status": "failure",
  "processing_time": 0.01,
  "errors": [
    {
      "code": "UNSUPPORTED_FORMAT",
      "message": "仅支持 PDF 文件，收到: .docx"
    }
  ]
}
```

**错误码：**

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `INVALID_REQUEST` | 400 | 缺少文件或文件名为空 |
| `EMPTY_FILE` | 400 | 上传文件为空 |
| `UNSUPPORTED_FORMAT` | 415 | 非 PDF 文件 |
| `FILE_TOO_LARGE` | 413 | 文件超过 50 MB 限制 |
| `EXTRACTION_FAILED` | 500 | PDF 解析失败 |

## 项目结构

```
AirReader/
├── src/main/java/com/norlandsoft/air/reader/
│   ├── Application.java                  -- Spring Boot 启动类
│   ├── controller/
│   │   └── ConvertController.java        -- REST 控制器（health + convert/file）
│   ├── model/
│   │   └── ConvertResponse.java          -- Docling 风格响应模型
│   └── service/
│       ├── OpenDataLoaderService.java    -- ODL 核心解析服务（进程内 JVM 调用）
│       ├── ExtractConfig.java            -- 解析配置选项
│       └── ExtractResult.java            -- 解析结果封装
├── src/main/resources/
│   └── application.properties            -- 服务配置（端口、上传限制）
├── Dockerfile                            -- 两阶段构建（Maven + JDK runtime）
├── docker-compose.yml                    -- 容器编排（端口 9103:8000）
└── pom.xml                               -- Maven 配置
```

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Java | 21 | 运行时 |
| Spring Boot | 3.3.5 | Web 框架 |
| OpenDataLoader PDF Core | 1.3.0 | PDF 解析引擎，进程内 JVM 调用 |

## 与 Docling-serve 的对比

| 维度 | AirReader | Docling-serve |
|------|---------------|---------------|
| 语言 | Java 21 | Python |
| 解析引擎 | OpenDataLoader | Docling (IBM) |
| API 端点 | `/api/v1/convert/file` | `/api/v1/convert/file` + `/v1alpha/convert/source` |
| 响应结构 | `document` + `status` + `errors` | `document` + `status` + `errors` |
| 文件参数名 | `files` | `files` |
| 输出格式 | md, text | md, json, html, text, doctags |
| 运行方式 | JVM 进程 | Python + PyTorch |

## 约束

- 仅支持 PDF 文件格式
- 文件大小上限 50 MB
- 无状态服务，不提供文档持久化存储
