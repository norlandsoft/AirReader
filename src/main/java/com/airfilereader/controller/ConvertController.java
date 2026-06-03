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
