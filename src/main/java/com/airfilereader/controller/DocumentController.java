package com.airfilereader.controller;

import com.airfilereader.model.ApiModels.*;
import com.airfilereader.service.OpenDataLoaderService;
import com.airfilereader.service.OpenDataLoaderService.ExtractionResult;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1")
public class DocumentController {

    private final OpenDataLoaderService loader = new OpenDataLoaderService();
    private final Map<String, ExtractionData> docStore = new ConcurrentHashMap<>();
    private static final Set<String> ALLOWED = Set.of(".pdf");
    private static final long MAX_SIZE = 50 * 1024 * 1024;

    @GetMapping("/health")
    public ResponseEntity<ApiResponse> health(HttpServletRequest req) {
        return ResponseEntity.ok(ApiResponse.success(HealthData.ok(), requestId(req), 0));
    }

    @PostMapping(value = "/documents/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ApiResponse> extract(
            HttpServletRequest req,
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "output_format", defaultValue = "markdown") String outputFormat,
            @RequestParam(value = "store", defaultValue = "false") boolean store) {

        String filename = file.getOriginalFilename();
        if (filename == null || filename.isBlank()) {
            return ResponseEntity.badRequest().body(
                ApiResponse.error(List.of(err(ErrorCode.INVALID_REQUEST, "No filename provided")), requestId(req)));
        }

        String suffix = filename.contains(".") ? filename.substring(filename.lastIndexOf('.')).toLowerCase() : "";
        if (!ALLOWED.contains(suffix)) {
            return ResponseEntity.status(415).body(
                ApiResponse.error(List.of(err(ErrorCode.UNSUPPORTED_FORMAT,
                    "File type '" + suffix + "' is not supported",
                    "OpenDataLoader only supports PDF files")), requestId(req)));
        }

        if (file.getSize() == 0) {
            return ResponseEntity.badRequest().body(
                ApiResponse.error(List.of(err(ErrorCode.EMPTY_FILE, "Uploaded file is empty")), requestId(req)));
        }

        if (file.getSize() > MAX_SIZE) {
            return ResponseEntity.status(413).body(
                ApiResponse.error(List.of(err(ErrorCode.FILE_TOO_LARGE,
                    "File size exceeds 50 MB limit")), requestId(req)));
        }

        long t0 = System.nanoTime();

        Path tmpFile = null;
        try {
            tmpFile = Files.createTempFile("upload_", ".pdf");
            file.transferTo(tmpFile.toFile());

            ExtractionResult result = loader.extract(tmpFile, filename);

            String text = result.markdown();
            if ("text".equals(outputFormat)) {
                text = stripMarkdown(text);
            }

            DocumentInfo docInfo = new DocumentInfo(filename, "pdf", "PDF", result.pageCount(), result.fileSizeBytes());
            ContentInfo contentInfo = new ContentInfo(outputFormat, text, text.length());
            ExtractionData data = new ExtractionData(docInfo, contentInfo);

            if (store) {
                docStore.put(UUID.randomUUID().toString(), data);
            }

            double elapsed = (System.nanoTime() - t0) / 1_000_000.0;
            return ResponseEntity.ok(ApiResponse.success(data, requestId(req), elapsed));

        } catch (Exception e) {
            double elapsed = (System.nanoTime() - t0) / 1_000_000.0;
            return ResponseEntity.status(500).body(
                ApiResponse.error(List.of(err(ErrorCode.EXTRACTION_FAILED,
                    "Document extraction failed", e.getMessage())), requestId(req)));
        } finally {
            if (tmpFile != null) { try { Files.deleteIfExists(tmpFile); } catch (IOException ignored) {} }
        }
    }

    @GetMapping("/documents/{docId}")
    public ResponseEntity<ApiResponse> getDocument(HttpServletRequest req, @PathVariable String docId) {
        ExtractionData data = docStore.get(docId);
        if (data == null) {
            return ResponseEntity.status(404).body(
                ApiResponse.error(List.of(err(ErrorCode.NOT_FOUND, "Document '" + docId + "' not found")), requestId(req)));
        }
        return ResponseEntity.ok(ApiResponse.success(data, requestId(req), 0));
    }

    private static String requestId(HttpServletRequest req) {
        String rid = req.getHeader("X-Request-ID");
        return (rid != null && !rid.isBlank()) ? rid : UUID.randomUUID().toString().replace("-", "");
    }

    private static ApiError err(ErrorCode code, String message) { return new ApiError(code, message, null); }
    private static ApiError err(ErrorCode code, String message, String detail) { return new ApiError(code, message, detail); }

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
}
