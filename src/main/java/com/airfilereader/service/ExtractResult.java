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

    /** 构建成功结果 */
    public static ExtractResult success(String markdown) {
        return new ExtractResult(true, markdown, null);
    }

    /** 构建失败结果 */
    public static ExtractResult failure(String error) {
        return new ExtractResult(false, null, error);
    }

    public boolean isSuccess() { return success; }
    public String getMarkdown() { return markdown; }
    public String getError() { return error; }
}
