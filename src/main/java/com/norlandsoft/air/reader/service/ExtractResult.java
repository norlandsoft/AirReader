package com.norlandsoft.air.reader.service;

import java.nio.file.Path;

/**
 * PDF 解析结果
 *
 * 成功时携带 ODL 输出目录（含 Markdown 文件和图片目录），
 * 由 Controller 流式打包为 zip 返回，无需将内容加载到内存。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
public class ExtractResult {

    private final boolean success;
    private final Path outputDir;
    private final String error;

    private ExtractResult(boolean success, Path outputDir, String error) {
        this.success = success;
        this.outputDir = outputDir;
        this.error = error;
    }

    /** 构建成功结果（携带 ODL 输出目录供 zip 打包） */
    public static ExtractResult success(Path outputDir) {
        return new ExtractResult(true, outputDir, null);
    }

    /** 构建失败结果 */
    public static ExtractResult failure(String error) {
        return new ExtractResult(false, null, error);
    }

    public boolean isSuccess() { return success; }
    public Path getOutputDir() { return outputDir; }
    public String getError() { return error; }
}
