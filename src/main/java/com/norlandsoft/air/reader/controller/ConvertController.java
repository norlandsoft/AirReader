package com.norlandsoft.air.reader.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.norlandsoft.air.reader.model.ConvertResponse;
import com.norlandsoft.air.reader.service.ExtractResult;
import com.norlandsoft.air.reader.service.OpenDataLoaderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 文档转换 REST 控制器
 *
 * - GET  /api/v1/health        — 健康检查
 * - POST /api/v1/convert/file  — 上传 PDF，返回 zip（Markdown + 图片）
 *
 * 所有响应均通过 StreamingResponseBody 返回，
 * Spring 的 StreamingResponseBodyReturnValueHandler 处理流式输出。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@RestController
public class ConvertController {

    private static final Logger log = LoggerFactory.getLogger(ConvertController.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final long MAX_SIZE = 50 * 1024 * 1024;

    private final OpenDataLoaderService service;

    public ConvertController(OpenDataLoaderService service) {
        this.service = service;
    }

    /**
     * 健康检查
     */
    @GetMapping("/api/v1/health")
    public ResponseEntity<HealthResponse> health() {
        return ResponseEntity.ok(new HealthResponse("healthy", "2.0.0"));
    }

    /**
     * 上传 PDF 文件，提取为 Markdown + 图片，打包为 zip 返回
     *
     * 成功：application/zip（流式）
     * 错误：application/json
     */
    @PostMapping(value = "/api/v1/convert/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<StreamingResponseBody> convertFile(@RequestParam("files") MultipartFile file) {

        long t0 = System.nanoTime();
        String filename = file.getOriginalFilename();

        // 校验
        if (filename == null || filename.isBlank()) {
            return err(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "缺少文件名", t0);
        }
        String lowerName = filename.toLowerCase();
        if (!lowerName.endsWith(".pdf")) {
            return err(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_FORMAT",
                    "仅支持 PDF 文件，收到: " + lowerName.substring(lowerName.lastIndexOf('.')), t0);
        }
        if (file.isEmpty()) {
            return err(HttpStatus.BAD_REQUEST, "EMPTY_FILE", "上传文件为空", t0);
        }
        if (file.getSize() > MAX_SIZE) {
            return err(HttpStatus.PAYLOAD_TOO_LARGE, "FILE_TOO_LARGE",
                    "文件大小超过 50 MB 限制", t0);
        }

        // 保存上传文件并解析
        Path tmpFile = null;
        try {
            tmpFile = Files.createTempFile("upload_", ".pdf");
            file.transferTo(tmpFile.toFile());

            ExtractResult result = service.extract(tmpFile);

            if (!result.isSuccess()) {
                return err(HttpStatus.INTERNAL_SERVER_ERROR, "EXTRACTION_FAILED",
                        result.getError(), t0);
            }

            // 流式返回 zip
            double elapsed = elapsedSec(t0);
            String baseName = filename.replaceAll("\\.(?i)pdf$", "");
            long fileSize = service.getFileSize(tmpFile);
            Path outputDir = result.getOutputDir();
            Path pdfRef = tmpFile;

            StreamingResponseBody body = out -> {
                try {
                    service.packageAsZip(out, outputDir, pdfRef, filename, fileSize, elapsed);
                } finally {
                    service.cleanupDir(outputDir);
                    try { Files.deleteIfExists(pdfRef); } catch (Exception ignored) {}
                }
            };

            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType("application/zip"))
                    .header("Content-Disposition", "attachment; filename=\"" + baseName + ".zip\"")
                    .body(body);

        } catch (Exception e) {
            log.error("文件处理异常: {}", e.getMessage(), e);
            return err(HttpStatus.INTERNAL_SERVER_ERROR, "EXTRACTION_FAILED",
                    "文件处理失败: " + e.getMessage(), t0);
        } finally {
            // 异常路径清理（正常路径在 zip 流回调的 finally 中清理）
            if (tmpFile != null) {
                try { Files.deleteIfExists(tmpFile); } catch (Exception ignored) {}
            }
        }
    }

    /**
     * 构建错误响应（通过 StreamingResponseBody 写入 JSON）
     */
    private ResponseEntity<StreamingResponseBody> err(HttpStatus status, String code, String message, long t0) {
        ConvertResponse body = ConvertResponse.failure(code, message, elapsedSec(t0));
        StreamingResponseBody stream = out -> {
            out.write(OBJECT_MAPPER.writeValueAsBytes(body));
        };
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .body(stream);
    }

    private double elapsedSec(long t0) {
        return Math.round((System.nanoTime() - t0) / 10_000_000.0) / 100.0;
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
