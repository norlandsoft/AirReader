# AirReader PDF 文档内容读取服务 — 设计文档

> 日期: 2026-06-03
> 作者: ChaiMingXu
> 状态: 待实施

---

## 1. 目标

将 JettoAuthor 项目中 `tools/extract` 包的 OpenDataLoader PDF 解析核心功能迁移到 AirReader 项目，实现一个无状态的 PDF→Markdown 转换服务。对外提供 Docling 风格的 REST API，供第三方服务调用。

## 2. 现状分析

### 2.1 JettoAuthor tools/extract 架构（源）

```
tools/extract/
├── ExtractUtils.java              -- ODL 核心封装，调用 OpenDataLoaderPDF.processFile()
├── ExtractResult.java             -- 解析结果 DTO (success/markdown/error)
├── ToolsExtractController.java    -- REST 接口 POST /api/tools/extract/file_parse
└── strategy/
    ├── PdfExtractStrategy.java    -- 策略接口
    └── OpenDataLoaderStrategy.java-- ODL 策略实现（InputStream→临时文件→ExtractUtils）
```

核心能力：
- 使用 `opendataloader-pdf-core` 1.3.0 Maven 依赖，进程内 JVM 调用
- 支持配置项：markdownWithHtml、markdownWithImages、keepLineBreaks、generateHtml、password
- 临时目录隔离并发，自动清理
- 多级 .md 文件查找（同名→任意→子目录）

### 2.2 AirReader 现有实现（待清理）

- Spring Boot 3.3.5 + Java 21
- 使用 `opendataloader-pdf-cli` 2.4.7（本地 jar，ProcessBuilder 子进程调用）
- 自定义 API 风格（非 Docling 风格）
- 包含文档存储功能（store=true, GET /documents/{docId}）

### 2.3 Docling API 风格（参考目标）

Docling-serve v0.3.0 的核心设计：
- 端点：`POST /v1alpha/convert/file`（multipart 上传）+ `GET /health`
- 响应结构：
  ```json
  {
    "document": { "md_content": "..." },
    "status": "success",
    "processing_time": 0.0,
    "errors": []
  }
  ```
- 参数通过 form field 传递（to_formats, do_ocr 等）

## 3. 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| ODL 调用方式 | 进程内调用（pdf-core） | 无子进程开销，性能更好，与 JettoAuthor 源实现一致 |
| API 端点 | health + convert/file | 仅需文件上传场景，不需要 URL/base64 端点 |
| 响应格式 | Docling 风格 | 对齐 Docling 的 document + status + errors 结构 |
| 解析参数 | ODL 核心参数子集 | 仅暴露 ODL 实际支持的选项，不模拟 Docling 不适用的参数 |
| 存储功能 | 移除 | 聚焦无状态转换服务，第三方自行管理文档存储 |
| 代码策略 | 完全清理重写 | 去除 CLI 依赖和旧代码，从零构建清晰架构 |

## 4. 架构设计

### 4.1 模块结构

```
src/main/java/com/airfilereader/
├── Application.java                  -- Spring Boot 启动类
├── controller/
│   └── ConvertController.java        -- REST 端点：health + convert/file
├── model/
│   ├── ConvertResponse.java          -- Docling 风格响应体
│   └── DocumentContent.java          -- 文档内容模型
└── service/
    └── OpenDataLoaderService.java    -- ODL 核心服务（从 ExtractUtils 移植）

src/main/resources/
└── application.properties            -- 配置文件
```

### 4.2 依赖变更

```xml
<!-- 移除 -->
<dependency>
    <groupId>org.opendataloader</groupId>
    <artifactId>opendataloader-pdf-cli</artifactId>
    <scope>system</scope>
    <systemPath>${project.basedir}/lib/opendataloader-pdf-cli.jar</systemPath>
</dependency>

<!-- 新增 -->
<dependency>
    <groupId>org.opendataloader</groupId>
    <artifactId>opendataloader-pdf-core</artifactId>
    <version>1.3.0</version>
</dependency>
```

### 4.3 API 设计

#### GET /health

健康检查端点。

**响应：**
```json
{
  "status": "healthy",
  "version": "2.0.0"
}
```

#### POST /v1alpha/convert/file

上传 PDF 文件，返回 Markdown 内容。

**请求：** `multipart/form-data`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| files | File | 是 | - | PDF 文件（单文件） |
| to_formats | String | 否 | "md" | 输出格式，可选值：md, text |
| markdown_with_html | Boolean | 否 | false | Markdown 中是否使用 HTML 标签渲染复杂元素 |
| markdown_with_images | Boolean | 否 | false | Markdown 中是否包含图片引用 |
| keep_line_breaks | Boolean | 否 | false | 是否保留原始换行符 |

**成功响应（200）：**
```json
{
  "document": {
    "md_content": "# 标题\n\n正文内容...",
    "text_content": null,
    "filename": "report.pdf",
    "page_count": 10,
    "file_size_bytes": 123456
  },
  "status": "success",
  "processing_time": 1.23,
  "errors": []
}
```

**失败响应（4xx/5xx）：**
```json
{
  "document": null,
  "status": "failure",
  "processing_time": 0.05,
  "errors": [
    {
      "code": "UNSUPPORTED_FORMAT",
      "message": "仅支持 PDF 文件"
    }
  ]
}
```

#### 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| INVALID_REQUEST | 400 | 缺少文件或文件名为空 |
| UNSUPPORTED_FORMAT | 415 | 非 PDF 文件 |
| EMPTY_FILE | 400 | 上传文件为空 |
| FILE_TOO_LARGE | 413 | 文件超过 50MB 限制 |
| EXTRACTION_FAILED | 500 | PDF 解析失败 |

### 4.4 核心服务设计（OpenDataLoaderService）

从 JettoAuthor 的 `ExtractUtils` 移植核心逻辑：

```
extract(Path pdfPath, ExtractConfig config) → ExtractResult
  1. 校验文件存在性和类型
  2. 创建临时输出目录
  3. 构建 ODL Config 对象
     - setOutputFolder(临时目录)
     - setGenerateMarkdown(true)
     - 按需设置 addImageToMarkdown/useHTMLInMarkdown/keepLineBreaks
  4. 调用 OpenDataLoaderPDF.processFile(inputPath, config)
  5. 从输出目录查找 .md 文件（同名优先 → 任意 .md → 子目录查找）
  6. 读取并返回 Markdown 内容
  7. finally 清理临时目录
```

### 4.5 清理范围

| 文件/目录 | 操作 |
|-----------|------|
| lib/ | 删除整个目录（含 opendataloader-pdf-cli.jar） |
| src/main/java/com/airfilereader/ | 删除所有现有 Java 文件 |
| src/main/resources/application.properties | 重写 |
| pom.xml | 重写（移除 CLI 依赖，新增 core 依赖） |
| Dockerfile | 更新（移除 CLI jar COPY） |
| docker-compose.yml | 保持不变（端口映射 9103:8000） |
| scripts/build.sh | 保持不变 |
| skills/document_extract/SKILL.md | 更新 API 端点描述 |
| README.md | 重写 |
| .dockerignore | 保持不变 |
| .gitignore | 保持不变 |

## 5. 文件清单

按实施顺序：

1. **清理旧文件** — 删除 lib/ 和 src/ 下所有 Java 文件
2. **pom.xml** — 重写依赖
3. **application.properties** — 重写配置
4. **OpenDataLoaderService.java** — 核心服务（移植 ExtractUtils）
5. **DocumentContent.java** — 响应模型
6. **ConvertResponse.java** — Docling 风格响应体
7. **ConvertController.java** — REST 控制器
8. **Application.java** — 启动类
9. **Dockerfile** — 更新构建流程
10. **README.md** — 更新文档
11. **SKILL.md** — 更新技能描述

## 6. 约束

- 仅支持 PDF 文件
- 文件大小上限 50MB
- 无状态服务，不提供文档持久化
- 端口：容器内 8000，对外映射 9103
