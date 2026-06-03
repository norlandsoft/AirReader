package com.norlandsoft.air.reader.service;

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
