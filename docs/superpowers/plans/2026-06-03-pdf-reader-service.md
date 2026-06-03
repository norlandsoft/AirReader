# AirReader PDF 文档内容读取服务 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 JettoAuthor tools/extract 的 OpenDataLoader PDF 解析核心迁移到 AirReader，实现 Docling 风格的 PDF→Markdown REST API 服务。

**Architecture:** 单体 Spring Boot 服务，进程内调用 opendataloader-pdf-core 库。请求通过 Controller 校验后交给 Service 层，Service 使用临时目录隔离并发、调用 ODL API 解析 PDF 并读取 Markdown 输出。响应对齐 Docling 的 document + status + errors 结构。

**Tech Stack:** Java 21, Spring Boot 3.3.5, opendataloader-pdf-core 1.3.0, Docker

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 删除 | `lib/opendataloader-pdf-cli.jar` | 旧的 CLI jar |
| 删除 | `src/main/java/com/airfilereader/Application.java` | 旧启动类 |
| 删除 | `src/main/java/com/airfilereader/controller/DocumentController.java` | 旧控制器 |
| 删除 | `src/main/java/com/airfilereader/model/ApiModels.java` | 旧模型 |
| 删除 | `src/main/java/com/airfilereader/service/OpenDataLoaderService.java` | 旧服务 |
| 重写 | `pom.xml` | 切换依赖为 pdf-core |
| 重写 | `src/main/resources/application.properties` | 简化配置 |
| 新建 | `src/main/java/com/airfilereader/Application.java` | 新启动类 |
| 新建 | `src/main/java/com/airfilereader/service/OpenDataLoaderService.java` | ODL 核心服务 |
| 新建 | `src/main/java/com/airfilereader/service/ExtractConfig.java` | 解析配置 |
| 新建 | `src/main/java/com/airfilereader/service/ExtractResult.java` | 解析结果 |
| 新建 | `src/main/java/com/airfilereader/model/ConvertResponse.java` | Docling 风格响应体 |
| 新建 | `src/main/java/com/airfilereader/controller/ConvertController.java` | REST 控制器 |
| 重写 | `Dockerfile` | 移除 lib COPY |
| 重写 | `README.md` | 更新文档 |
| 更新 | `skills/document_extract/SKILL.md` | 更新 API 描述 |

---

### Task 1: 清理旧代码和依赖

**Files:**
- 删除: `lib/` 目录
- 删除: `src/main/java/com/airfilereader/controller/DocumentController.java`
- 删除: `src/main/java/com/airfilereader/model/ApiModels.java`
- 删除: `src/main/java/com/airfilereader/service/OpenDataLoaderService.java`
- 删除: `src/main/java/com/airfilereader/Application.java`
- 重写: `pom.xml`

- [ ] **Step 1: 删除旧的源码文件和 lib 目录**

```bash
cd /opt/AirReader
rm -rf lib/
rm -f src/main/java/com/airfilereader/controller/DocumentController.java
rm -f src/main/java/com/airfilereader/model/ApiModels.java
rm -f src/main/java/com/airfilereader/service/OpenDataLoaderService.java
rm -f src/main/java/com/airfilereader/Application.java
```

- [ ] **Step 2: 重写 pom.xml，切换到 opendataloader-pdf-core 依赖**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.airfilereader</groupId>
    <artifactId>air-filereader</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>
    <name>AirFileReader</name>
    <description>PDF to Markdown conversion service powered by OpenDataLoader</description>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.opendataloader</groupId>
            <artifactId>opendataloader-pdf-core</artifactId>
            <version>1.3.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

- [ ] **Step 3: 重写 application.properties**

```properties
server.port=8000
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=60MB
```

- [ ] **Step 4: 提交清理**

```bash
cd /opt/AirReader
git add -A
git commit -m "refactor: 清理旧代码和 CLI 依赖，切换到 opendataloader-pdf-core"
```

---

### Task 2: 实现 ODL 核心服务层

**Files:**
- 新建: `src/main/java/com/airfilereader/service/ExtractConfig.java`
- 新建: `src/main/java/com/airfilereader/service/ExtractResult.java`
- 新建: `src/main/java/com/airfilereader/service/OpenDataLoaderService.java`

- [ ] **Step 1: 创建 ExtractConfig 解析配置类**

```java
package com.airfilereader.service;

/**
 * OpenDataLoader PDF 解析配置
 *
 * 提供常用的解析选项，控制输出格式和行为。
 * 所有选项都有合理的默认值，通常使用默认配置即可。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
public class ExtractConfig {

    /** 是否在 Markdown 中包含图片引用，默认不包含 */
    private boolean markdownWithImages = false;

    /** 是否在 Markdown 中使用 HTML 标签渲染复杂元素（如表格），默认不使用 */
    private boolean markdownWithHtml = false;

    /** 是否保留原始换行符，默认移除换行和连字符 */
    private boolean keepLineBreaks = false;

    public boolean isMarkdownWithImages() { return markdownWithImages; }
    public ExtractConfig setMarkdownWithImages(boolean v) { this.markdownWithImages = v; return this; }

    public boolean isMarkdownWithHtml() { return markdownWithHtml; }
    public ExtractConfig setMarkdownWithHtml(boolean v) { this.markdownWithHtml = v; return this; }

    public boolean isKeepLineBreaks() { return keepLineBreaks; }
    public ExtractConfig setKeepLineBreaks(boolean v) { this.keepLineBreaks = v; return this; }
}
```

- [ ] **Step 2: 创建 ExtractResult 解析结果类**

```java
package com.airfilereader.service;

/**
 * PDF 解析结果
 *
 * 封装 OpenDataLoader 解析 PDF 后返回的结果，
 * 包含提取的 Markdown 内容和错误信息。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
public class ExtractResult {

    private final boolean success;
    private final String markdown;
    private final String error;

    private ExtractResult(boolean success, String markdown, String error) {
        this.success = success;
        this.markdown = markdown;
        this.error = error;
    }

    public static ExtractResult success(String markdown) {
        return new ExtractResult(true, markdown, null);
    }

    public static ExtractResult failure(String error) {
        return new ExtractResult(false, null, error);
    }

    public boolean isSuccess() { return success; }
    public String getMarkdown() { return markdown; }
    public String getError() { return error; }
}
```

- [ ] **Step 3: 创建 OpenDataLoaderService 核心服务**

从 JettoAuthor 的 ExtractUtils 移植核心逻辑，使用 opendataloader-pdf-core 进程内调用。

```java
package com.airfilereader.service;

import org.opendataloader.pdf.api.Config;
import org.opendataloader.pdf.api.OpenDataLoaderPDF;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

/**
 * OpenDataLoader PDF 解析核心服务
 *
 * 封装 opendataloader-pdf-core 库，提供 PDF 到 Markdown 的转换能力。
 * 使用进程内 JVM 调用 OpenDataLoaderPDF.processFile()，无子进程开销。
 *
 * 设计思路：
 * - 每次解析使用独立的临时目录，确保并发安全
 * - 解析完成后自动读取生成的 Markdown 文件并返回字符串内容
 * - 通过 try-with-resources 和 finally 块确保临时目录被清理
 * - 多级 .md 文件查找策略：同名优先 → 任意 .md → 子目录查找
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@Service
public class OpenDataLoaderService {

    private static final Logger log = LoggerFactory.getLogger(OpenDataLoaderService.class);

    /**
     * 将 PDF 文件解析为 Markdown 文本
     *
     * @param pdfPath PDF 文件路径
     * @param config  解析配置，可为 null 使用默认值
     * @return 解析结果
     */
    public ExtractResult extract(Path pdfPath, ExtractConfig config) {
        if (!Files.exists(pdfPath)) {
            return ExtractResult.failure("PDF 文件不存在: " + pdfPath);
        }
        if (!Files.isRegularFile(pdfPath)) {
            return ExtractResult.failure("路径不是有效的文件: " + pdfPath);
        }

        Path outputDir = null;
        try {
            outputDir = Files.createTempDirectory("odl-");
            String markdown = doProcess(pdfPath, outputDir, config != null ? config : new ExtractConfig());

            if (markdown == null || markdown.isEmpty()) {
                return ExtractResult.failure("PDF 解析完成但未生成 Markdown 内容");
            }

            log.info("PDF 解析完成: file={}, length={}", pdfPath.getFileName(), markdown.length());
            return ExtractResult.success(markdown);
        } catch (Exception e) {
            log.error("PDF 解析失败: file={}, error={}", pdfPath.getFileName(), e.getMessage(), e);
            return ExtractResult.failure("PDF 解析失败: " + e.getMessage());
        } finally {
            if (outputDir != null) {
                cleanupDir(outputDir);
            }
        }
    }

    /**
     * 获取 PDF 文件大小（字节）
     */
    public long getFileSize(Path pdfPath) {
        try {
            return Files.size(pdfPath);
        } catch (IOException e) {
            return 0;
        }
    }

    /**
     * 执行 PDF 解析并读取结果
     */
    private String doProcess(Path inputPath, Path outputDir, ExtractConfig config) throws IOException {
        log.debug("开始解析 PDF: {} -> {}", inputPath, outputDir);

        Config odlConfig = new Config();
        odlConfig.setOutputFolder(outputDir.toString());
        odlConfig.setGenerateMarkdown(true);

        if (config.isMarkdownWithImages()) {
            odlConfig.setAddImageToMarkdown(true);
        }
        if (config.isMarkdownWithHtml()) {
            odlConfig.setUseHTMLInMarkdown(true);
        }
        if (config.isKeepLineBreaks()) {
            odlConfig.setKeepLineBreaks(true);
        }

        OpenDataLoaderPDF.processFile(inputPath.toString(), odlConfig);

        String markdown = readMarkdownOutput(outputDir, inputPath);
        log.debug("PDF 解析完成，Markdown 长度: {}", markdown != null ? markdown.length() : 0);
        return markdown;
    }

    /**
     * 从输出目录中查找并读取 Markdown 文件
     *
     * 查找策略：同名 .md → 任意 .md → 子目录中 .md
     */
    private String readMarkdownOutput(Path outputDir, Path inputPath) throws IOException {
        // 优先查找同名 .md 文件
        String baseName = inputPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");
        Path expectedMd = outputDir.resolve(baseName + ".md");
        if (Files.exists(expectedMd)) {
            return Files.readString(expectedMd, StandardCharsets.UTF_8);
        }

        // 回退：输出目录中的任意 .md 文件
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(outputDir, "*.md")) {
            for (Path mdFile : stream) {
                return Files.readString(mdFile, StandardCharsets.UTF_8);
            }
        }

        // 尝试在子目录中查找
        try (Stream<Path> walk = Files.walk(outputDir)) {
            return walk
                    .filter(p -> p.toString().endsWith(".md"))
                    .findFirst()
                    .map(p -> {
                        try {
                            return Files.readString(p, StandardCharsets.UTF_8);
                        } catch (IOException e) {
                            log.warn("读取 Markdown 文件失败: {}", p, e);
                            return null;
                        }
                    })
                    .orElse(null);
        }
    }

    /**
     * 递归删除临时目录及其所有内容
     */
    private void cleanupDir(Path dir) {
        if (dir == null || !Files.exists(dir)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(dir)) {
            walk.sorted(Comparator.reverseOrder())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException e) {
                            log.warn("清理临时文件失败: {}", p, e);
                        }
                    });
        } catch (IOException e) {
            log.warn("清理临时目录失败: {}", dir, e);
        }
    }
}
```

- [ ] **Step 4: 提交核心服务**

```bash
cd /opt/AirReader
git add -A
git commit -m "feat: 实现 OpenDataLoader 核心服务层（进程内 PDF 解析）"
```

---

### Task 3: 实现 Docling 风格响应模型

**Files:**
- 新建: `src/main/java/com/airfilereader/model/ConvertResponse.java`

- [ ] **Step 1: 创建 Docling 风格的响应模型**

对齐 Docling 的响应结构：document + status + processing_time + errors。

```java
package com.airfilereader.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Docling 风格的文档转换响应体
 *
 * 响应结构对齐 Docling-serve 的 JSON 格式：
 * - document: 文档内容（md_content, filename, page_count, file_size_bytes）
 * - status: success | failure
 * - processing_time: 处理耗时（秒）
 * - errors: 错误列表（仅失败时填充）
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ConvertResponse {

    /** 文档内容 */
    private DocumentContent document;

    /** 状态：success 或 failure */
    private String status;

    /** 处理耗时（秒） */
    private double processingTime;

    /** 错误列表 */
    private List<ConvertError> errors;

    public DocumentContent getDocument() { return document; }
    public void setDocument(DocumentContent document) { this.document = document; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public double getProcessingTime() { return processingTime; }
    public void setProcessingTime(double processingTime) { this.processingTime = processingTime; }

    public List<ConvertError> getErrors() { return errors; }
    public void setErrors(List<ConvertError> errors) { this.errors = errors; }

    /**
     * 构建成功响应
     */
    public static ConvertResponse success(DocumentContent document, double processingTimeSec) {
        ConvertResponse resp = new ConvertResponse();
        resp.setStatus("success");
        resp.setDocument(document);
        resp.setProcessingTime(processingTimeSec);
        resp.setErrors(Collections.emptyList());
        return resp;
    }

    /**
     * 构建失败响应
     */
    public static ConvertResponse failure(String errorCode, String message, double processingTimeSec) {
        ConvertResponse resp = new ConvertResponse();
        resp.setStatus("failure");
        resp.setProcessingTime(processingTimeSec);
        List<ConvertError> errors = new ArrayList<>();
        errors.add(new ConvertError(errorCode, message));
        resp.setErrors(errors);
        return resp;
    }

    /**
     * 文档内容模型
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class DocumentContent {

        /** Markdown 内容 */
        private String mdContent;

        /** 纯文本内容（仅 to_formats=text 时填充） */
        private String textContent;

        /** 原始文件名 */
        private String filename;

        /** 页数（ODL 当前不提供此值，默认 0） */
        private int pageCount;

        /** 文件大小（字节） */
        private long fileSizeBytes;

        public String getMdContent() { return mdContent; }
        public void setMdContent(String mdContent) { this.mdContent = mdContent; }

        public String getTextContent() { return textContent; }
        public void setTextContent(String textContent) { this.textContent = textContent; }

        public String getFilename() { return filename; }
        public void setFilename(String filename) { this.filename = filename; }

        public int getPageCount() { return pageCount; }
        public void setPageCount(int pageCount) { this.pageCount = pageCount; }

        public long getFileSizeBytes() { return fileSizeBytes; }
        public void setFileSizeBytes(long fileSizeBytes) { this.fileSizeBytes = fileSizeBytes; }
    }

    /**
     * 转换错误
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class ConvertError {

        /** 错误码 */
        private String code;

        /** 错误描述 */
        private String message;

        public ConvertError() {}

        public ConvertError(String code, String message) {
            this.code = code;
            this.message = message;
        }

        public String getCode() { return code; }
        public void setCode(String code) { this.code = code; }

        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
    }
}
```

- [ ] **Step 2: 提交响应模型**

```bash
cd /opt/AirReader
git add -A
git commit -m "feat: 实现 Docling 风格响应模型"
```

---

### Task 4: 实现 REST 控制器

**Files:**
- 新建: `src/main/java/com/airfilereader/controller/ConvertController.java`

- [ ] **Step 1: 创建 ConvertController**

对齐 Docling 的端点风格：`POST /v1alpha/convert/file` + `GET /health`。

```java
package com.airfilereader.controller;

import com.airfilereader.model.ConvertResponse;
import com.airfilereader.model.ConvertResponse.DocumentContent;
import com.airfilereader.service.ExtractConfig;
import com.airfilereader.service.ExtractResult;
import com.airfilereader.service.OpenDataLoaderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 文档转换 REST 控制器
 *
 * 对齐 Docling-serve 的 API 风格：
 * - GET  /health                  — 健康检查
 * - POST /v1alpha/convert/file    — 上传 PDF，返回 Markdown
 *
 * 端点路径和响应结构与 Docling-serve v0.3.0 保持一致，
 * 参数精简为 OpenDataLoader 实际支持的选项。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@RestController
public class ConvertController {

    private static final Logger log = LoggerFactory.getLogger(ConvertController.class);
    private static final long MAX_SIZE = 50 * 1024 * 1024;

    private final OpenDataLoaderService service;

    public ConvertController(OpenDataLoaderService service) {
        this.service = service;
    }

    /**
     * 健康检查
     */
    @GetMapping("/health")
    public ResponseEntity<HealthResponse> health() {
        return ResponseEntity.ok(new HealthResponse("healthy", "2.0.0"));
    }

    /**
     * 上传 PDF 文件，转换为 Markdown
     *
     * 端点路径对齐 Docling-serve 的 /v1alpha/convert/file。
     * 请求格式为 multipart/form-data，支持以下参数：
     * - files: PDF 文件（必填）
     * - to_formats: 输出格式，md 或 text（默认 md）
     * - markdown_with_html: Markdown 中使用 HTML 标签（默认 false）
     * - markdown_with_images: Markdown 中包含图片引用（默认 false）
     * - keep_line_breaks: 保留原始换行符（默认 false）
     */
    @PostMapping(value = "/v1alpha/convert/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ConvertResponse> convertFile(
            @RequestParam("files") MultipartFile file,
            @RequestParam(value = "to_formats", defaultValue = "md") String toFormats,
            @RequestParam(value = "markdown_with_html", defaultValue = "false") boolean markdownWithHtml,
            @RequestParam(value = "markdown_with_images", defaultValue = "false") boolean markdownWithImages,
            @RequestParam(value = "keep_line_breaks", defaultValue = "false") boolean keepLineBreaks) {

        long t0 = System.nanoTime();
        String filename = file.getOriginalFilename();

        // 校验文件名
        if (filename == null || filename.isBlank()) {
            return err(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "缺少文件名", t0);
        }

        // 校验文件类型
        String lowerName = filename.toLowerCase();
        if (!lowerName.endsWith(".pdf")) {
            return err(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_FORMAT",
                    "仅支持 PDF 文件，收到: " + lowerName.substring(lowerName.lastIndexOf('.')), t0);
        }

        // 校验文件大小
        if (file.isEmpty()) {
            return err(HttpStatus.BAD_REQUEST, "EMPTY_FILE", "上传文件为空", t0);
        }
        if (file.getSize() > MAX_SIZE) {
            return err(HttpStatus.PAYLOAD_TOO_LARGE, "FILE_TOO_LARGE",
                    "文件大小超过 50 MB 限制", t0);
        }

        // 保存为临时文件并解析
        Path tmpFile = null;
        try {
            tmpFile = Files.createTempFile("upload_", ".pdf");
            file.transferTo(tmpFile.toFile());

            ExtractConfig config = new ExtractConfig()
                    .setMarkdownWithHtml(markdownWithHtml)
                    .setMarkdownWithImages(markdownWithImages)
                    .setKeepLineBreaks(keepLineBreaks);

            ExtractResult result = service.extract(tmpFile, config);

            double elapsed = elapsedSec(t0);

            if (!result.isSuccess()) {
                return err(HttpStatus.INTERNAL_SERVER_ERROR, "EXTRACTION_FAILED",
                        result.getError(), t0);
            }

            String mdContent = result.getMarkdown();
            String textContent = null;

            // 如果请求纯文本格式，从 Markdown 中去除格式标记
            if ("text".equalsIgnoreCase(toFormats)) {
                textContent = stripMarkdown(mdContent);
            }

            DocumentContent doc = new DocumentContent();
            doc.setMdContent(mdContent);
            doc.setTextContent(textContent);
            doc.setFilename(filename);
            doc.setPageCount(0);
            doc.setFileSizeBytes(service.getFileSize(tmpFile));

            return ResponseEntity.ok(ConvertResponse.success(doc, elapsed));

        } catch (Exception e) {
            log.error("文件处理异常: {}", e.getMessage(), e);
            return err(HttpStatus.INTERNAL_SERVER_ERROR, "EXTRACTION_FAILED",
                    "文件处理失败: " + e.getMessage(), t0);
        } finally {
            if (tmpFile != null) {
                try { Files.deleteIfExists(tmpFile); } catch (Exception ignored) {}
            }
        }
    }

    /**
     * 构建错误响应
     */
    private ResponseEntity<ConvertResponse> err(HttpStatus status, String code, String message, long t0) {
        return ResponseEntity.status(status)
                .body(ConvertResponse.failure(code, message, elapsedSec(t0)));
    }

    /**
     * 计算耗时（秒），保留两位小数
     */
    private double elapsedSec(long t0) {
        return Math.round((System.nanoTime() - t0) / 10_000_000.0) / 100.0;
    }

    /**
     * 去除 Markdown 格式标记，转为纯文本
     */
    private static String stripMarkdown(String text) {
        return text
                .replaceAll("(?m)^#{1,6}\\s+", "")
                .replaceAll("\\*{1,3}([^*]+)\\*{1,3}", "$1")
                .replaceAll("_{1,3}([^_]+)_{1,3}", "$1")
                .replaceAll("\\[([^\\]]*)\\]\\([^)]*\\)", "$1")
                .replaceAll("`{1,3}[^`]*`{1,3}", "")
                .replaceAll("(?m)^>\\s?", "")
                .replaceAll("(?m)^[-*_]{3,}\\s*$", "")
                .replaceAll("\\n{3,}", "\n\n")
                .trim();
    }

    /**
     * 健康检查响应
     */
    public static class HealthResponse {
        private final String status;
        private final String version;

        public HealthResponse(String status, String version) {
            this.status = status;
            this.version = version;
        }

        public String getStatus() { return status; }
        public String getVersion() { return version; }
    }
}
```

- [ ] **Step 2: 提交控制器**

```bash
cd /opt/AirReader
git add -A
git commit -m "feat: 实现 Docling 风格 REST 控制器（health + convert/file）"
```

---

### Task 5: 实现启动类

**Files:**
- 新建: `src/main/java/com/airfilereader/Application.java`

- [ ] **Step 1: 创建干净的 Spring Boot 启动类**

```java
package com.airfilereader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * AirFileReader 启动类
 *
 * PDF 文档内容读取服务，基于 OpenDataLoader 将 PDF 转换为 Markdown。
 * 对外提供 Docling 风格的 REST API。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

- [ ] **Step 2: 提交启动类**

```bash
cd /opt/AirReader
git add -A
git commit -m "feat: 新建 Spring Boot 启动类"
```

---

### Task 6: 更新 Dockerfile

**Files:**
- 重写: `Dockerfile`

- [ ] **Step 1: 重写 Dockerfile，移除 lib COPY**

不再需要 CLI jar，移除 lib 相关的 COPY 行。

```dockerfile
# ---- Build stage: compile with Maven ----
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build

COPY pom.xml .
RUN mvn dependency:go-offline -q

COPY src/ src/
RUN mvn clean package -DskipTests -q

# ---- Runtime stage: JDK only ----
FROM eclipse-temurin:21-jdk-alpine

WORKDIR /app

RUN addgroup -S appuser && adduser -S appuser -G appuser

COPY --from=builder /build/target/air-filereader-2.0.0.jar ./app.jar

RUN mkdir -p /data && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8000/health || exit 1

CMD ["java", "-jar", "app.jar"]
```

- [ ] **Step 2: 更新 docker-compose.yml 的健康检查路径**

将 healthcheck 从 `/api/v1/health` 改为 `/health`。

```yaml
services:
  air-filereader:
    build:
      context: .
      dockerfile: Dockerfile
    image: air-filereader:latest
    container_name: filereader.air
    ports:
      - "9103:8000"
    environment:
      - JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64
    volumes:
      - ./data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 3: 提交 Docker 更新**

```bash
cd /opt/AirReader
git add -A
git commit -m "refactor: 更新 Dockerfile 和 docker-compose（移除 lib COPY，更新 health 路径）"
```

---

### Task 7: 更新文档

**Files:**
- 重写: `README.md`
- 更新: `skills/document_extract/SKILL.md`

- [ ] **Step 1: 重写 README.md**

```markdown
# AirFileReader

PDF 文档内容读取服务 — 基于 OpenDataLoader 将 PDF 转换为 Markdown，通过 Docling 风格的 REST API 对外提供服务。

## 功能

- **PDF 提取**：使用 OpenDataLoader 进程内解析，将 PDF 内容转换为 Markdown
- **Docling 风格 API**：对齐 Docling-serve 的端点路径和响应结构
- **容器化部署**：提供 Dockerfile 和 docker-compose，一键构建和部署

## 快速开始

### Docker 部署

```bash
# 使用 docker compose
docker compose up -d

# 或手动构建
docker build -t air-filereader:latest .
docker run -p 9103:8000 air-filereader:latest
```

### 本地运行

```bash
mvn spring-boot:run
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/v1alpha/convert/file` | 上传 PDF，返回 Markdown |

### 示例

```bash
# 健康检查
curl http://localhost:9103/health

# 提取 PDF 内容为 Markdown
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf"

# 提取为纯文本
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf" \
  -F "to_formats=text"

# 启用 HTML 标签和图片引用
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf" \
  -F "markdown_with_html=true" \
  -F "markdown_with_images=true"
```

## 项目结构

```
AirFileReader/
├── src/main/java/com/airfilereader/
│   ├── Application.java                  -- Spring Boot 启动类
│   ├── controller/
│   │   └── ConvertController.java        -- REST 端点
│   ├── model/
│   │   └── ConvertResponse.java          -- Docling 风格响应模型
│   └── service/
│       ├── OpenDataLoaderService.java    -- ODL 核心解析服务
│       ├── ExtractConfig.java            -- 解析配置
│       └── ExtractResult.java            -- 解析结果
├── Dockerfile
├── docker-compose.yml
└── pom.xml
```
```

- [ ] **Step 2: 更新 SKILL.md**

```markdown
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
```

- [ ] **Step 3: 提交文档更新**

```bash
cd /opt/AirReader
git add -A
git commit -m "docs: 更新 README 和 SKILL.md，对齐新的 API 设计"
```

---

### Task 8: 构建验证

**Files:** 无新文件

- [ ] **Step 1: 本地 Maven 构建**

```bash
cd /opt/AirReader
mvn clean package -DskipTests
```

预期：BUILD SUCCESS，生成 `target/air-filereader-2.0.0.jar`

- [ ] **Step 2: 启动服务并验证 health 端点**

```bash
java -jar target/air-filereader-2.0.0.jar &
sleep 5
curl -s http://localhost:8000/health | python3 -m json.tool
```

预期响应：
```json
{
  "status": "healthy",
  "version": "2.0.0"
}
```

- [ ] **Step 3: 验证 PDF 转换端点**

```bash
# 使用任意 PDF 文件测试
curl -s -X POST http://localhost:8000/v1alpha/convert/file \
  -F "files=@test.pdf" | python3 -m json.tool
```

预期响应包含 `status: "success"` 和 `document.md_content` 非空。

- [ ] **Step 4: 停止服务，提交最终状态**

```bash
kill %1
```
