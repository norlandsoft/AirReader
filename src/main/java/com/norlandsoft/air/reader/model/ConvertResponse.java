package com.norlandsoft.air.reader.model;

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
