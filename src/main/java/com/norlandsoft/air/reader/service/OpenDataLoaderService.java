package com.norlandsoft.air.reader.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.multipdf.PageExtractor;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.opendataloader.pdf.api.Config;
import org.opendataloader.pdf.api.OpenDataLoaderPDF;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * OpenDataLoader PDF 解析核心服务
 *
 * 封装 opendataloader-pdf-core 库，提供 PDF 到 Markdown 的转换能力。
 *
 * 行为固定：
 * - 始终提取图片为独立 PNG 文件（原始分辨率，不压缩）
 * - 将 Markdown 文件 + 图片目录流式打包为 zip 返回
 * - 不将 markdown 或图片内容加载到 Java 堆内存
 *
 * 大文档处理：
 * - 超过 CHUNK_SIZE 页的 PDF 自动分片处理
 * - 使用 PDFBox PageExtractor 拆分，每片独立调用 ODL
 * - 合并所有分片的 markdown 和图片为统一输出
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@Service
public class OpenDataLoaderService {

    private static final Logger log = LoggerFactory.getLogger(OpenDataLoaderService.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /** 每片最大页数，超过此值触发分片处理 */
    private static final int CHUNK_SIZE = 10;

    /**
     * 将 PDF 文件解析为 Markdown + 图片，返回 ODL 输出目录
     *
     * 大文档自动分片处理，对调用方透明。
     *
     * @param pdfPath PDF 文件路径
     * @return 解析结果（成功时携带 outputDir，失败时携带 error）
     */
    public ExtractResult extract(Path pdfPath) {
        if (!Files.exists(pdfPath)) {
            return ExtractResult.failure("PDF 文件不存在: " + pdfPath);
        }
        if (!Files.isRegularFile(pdfPath)) {
            return ExtractResult.failure("路径不是有效的文件: " + pdfPath);
        }

        Path outputDir = null;
        try {
            outputDir = Files.createTempDirectory("odl-");

            // 检测页数，决定是否分片
            int totalPages = getPdfPageCount(pdfPath);
            log.info("PDF 文件: {}, 总页数: {}", pdfPath.getFileName(), totalPages);

            if (totalPages <= CHUNK_SIZE) {
                // 小文档：直接处理
                doProcess(pdfPath, outputDir);
            } else {
                // 大文档：分片处理
                processInChunks(pdfPath, outputDir, totalPages);
            }

            log.info("PDF 解析完成: file={}, pages={}, outputDir={}", pdfPath.getFileName(), totalPages, outputDir);
            return ExtractResult.success(outputDir);
        } catch (Exception e) {
            log.error("PDF 解析失败: file={}, error={}", pdfPath.getFileName(), e.getMessage(), e);
            cleanupDir(outputDir);
            return ExtractResult.failure("PDF 解析失败: " + e.getMessage());
        }
    }

    /**
     * 获取 PDF 页数（使用 PDFBox 内存映射方式，不全部加载到堆）
     */
    private int getPdfPageCount(Path pdfPath) throws IOException {
        try (PDDocument doc = Loader.loadPDF(pdfPath.toFile())) {
            return doc.getNumberOfPages();
        }
    }

    /**
     * 分片处理大 PDF
     *
     * 使用 PDFBox PageExtractor 按页数拆分，每片独立调用 ODL 处理。
     * 处理完一片后立即释放资源，控制峰值内存。
     */
    private void processInChunks(Path pdfPath, Path outputDir, int totalPages) throws IOException {
        log.info("分片处理: {} 页, 每片 {} 页, 共 {} 片", totalPages, CHUNK_SIZE,
                (totalPages + CHUNK_SIZE - 1) / CHUNK_SIZE);

        String baseName = pdfPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");

        // 用于收集所有分片的 markdown 内容
        StringBuilder mergedMarkdown = new StringBuilder();

        try (PDDocument sourceDoc = Loader.loadPDF(pdfPath.toFile())) {
            int chunkIndex = 0;

            for (int startPage = 1; startPage <= totalPages; startPage += CHUNK_SIZE) {
                int endPage = Math.min(startPage + CHUNK_SIZE - 1, totalPages);
                chunkIndex++;

                log.info("处理分片 {}/{}: 页 {}-{}", chunkIndex,
                        (totalPages + CHUNK_SIZE - 1) / CHUNK_SIZE, startPage, endPage);

                // 1. 提取子文档并保存到临时文件
                PageExtractor extractor = new PageExtractor(sourceDoc, startPage, endPage);
                Path chunkFile = outputDir.resolve("chunk_" + chunkIndex + ".pdf");

                try (PDDocument chunkDoc = extractor.extract()) {
                    chunkDoc.save(chunkFile.toFile());
                }

                // 2. 在子目录中处理分片
                Path chunkOutputDir = outputDir.resolve("chunk_" + chunkIndex + "_out");
                Files.createDirectories(chunkOutputDir);

                try {
                    doProcess(chunkFile, chunkOutputDir);
                } catch (Exception e) {
                    log.warn("分片 {}/{} 处理失败: {}", chunkIndex, chunkIndex, e.getMessage());
                    // 单片失败不中断整体处理
                }

                // 3. 读取分片 markdown 内容，修正图片引用加上分片前缀
                Path chunkMd = findMarkdownFileInDir(chunkOutputDir);
                if (chunkMd != null && Files.exists(chunkMd)) {
                    String content = Files.readString(chunkMd, StandardCharsets.UTF_8);
                    if (!content.isEmpty()) {
                        if (mergedMarkdown.length() > 0) {
                            mergedMarkdown.append("\n\n---\n\n");
                        }
                        // 将图片引用中的文件名加上 chunk_N_ 前缀，与实际磁盘文件名一致
                        mergedMarkdown.append(prefixImageRefs(content, chunkIndex));
                    }
                }

                // 4. 收集分片图片到主图片目录
                collectChunkImages(chunkOutputDir, outputDir, baseName, chunkIndex);

                // 5. 清理分片临时文件
                Files.deleteIfExists(chunkFile);
                cleanupDir(chunkOutputDir);
            }
        }

        // 写入合并后的 markdown 文件
        Path mergedMdFile = outputDir.resolve(baseName + ".md");
        Files.writeString(mergedMdFile, mergedMarkdown.toString(), StandardCharsets.UTF_8);
        log.info("分片合并完成: {} 字符, {} 图片", mergedMarkdown.length(),
                countImages(outputDir.resolve(baseName + "_images")));
    }

    /**
     * 为 markdown 中的图片引用文件名添加分片前缀
     *
     * ODL 输出的图片引用如 ![alt](xxx_images/imageFile1.png)
     * 加前缀后变为 ![alt](xxx_images/chunk_3_imageFile1.png)
     * 与 collectChunkImages 中实际保存的文件名一致
     */
    private String prefixImageRefs(String markdown, int chunkIndex) {
        String prefix = "chunk_" + chunkIndex + "_";
        // 匹配 ![alt](..._images/文件名) 并在文件名前加前缀
        return markdown.replaceAll(
            "!\\[([^\\]]*)\\]\\(([^)]*_images/)([^/)]+)\\)",
            "![$1]($2" + prefix + "$3)"
        );
    }

    /**
     * 收集分片中的图片文件到主图片目录
     *
     * 将 chunk_N_out/*_images/ 中的所有图片移动到主输出目录的 baseName_images/
     * 为避免重名冲突，给文件名添加分片前缀。
     */
    private void collectChunkImages(Path chunkOutputDir, Path outputDir, String baseName, int chunkIndex) throws IOException {
        Path mainImagesDir = outputDir.resolve(baseName + "_images");

        // 查找分片输出中的图片目录（可能是 *_images/）
        try (Stream<Path> walk = Files.walk(chunkOutputDir)) {
            walk.filter(p -> Files.isDirectory(p) && p.getFileName().toString().endsWith("_images"))
                .findFirst()
                .ifPresent(imagesDir -> {
                    try {
                        Files.createDirectories(mainImagesDir);
                        try (Stream<Path> imgFiles = Files.list(imagesDir)) {
                            imgFiles.filter(p -> !Files.isDirectory(p))
                                .forEach(imgFile -> {
                                    // 添加分片前缀避免重名: chunk_3_imageFile1.png
                                    String newName = "chunk_" + chunkIndex + "_" + imgFile.getFileName().toString();
                                    Path target = mainImagesDir.resolve(newName);
                                    try {
                                        Files.copy(imgFile, target, StandardCopyOption.REPLACE_EXISTING);
                                    } catch (IOException e) {
                                        log.warn("复制图片失败: {} -> {}", imgFile, target, e);
                                    }
                                });
                        }
                    } catch (IOException e) {
                        log.warn("收集图片失败: {}", imagesDir, e);
                    }
                });
        }
    }

    /**
     * 统计图片目录中的文件数量
     */
    private int countImages(Path imagesDir) {
        if (!Files.isDirectory(imagesDir)) return 0;
        try (Stream<Path> list = Files.list(imagesDir)) {
            return (int) list.filter(p -> !Files.isDirectory(p)).count();
        } catch (IOException e) {
            return 0;
        }
    }

    /**
     * 将 ODL 输出目录流式打包为 zip 写入 OutputStream
     */
    public void packageAsZip(OutputStream out, Path outputDir, Path inputPath,
                             String filename, long fileSizeBytes, double processingTime) throws IOException {
        String baseName = inputPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");

        try (ZipOutputStream zos = new ZipOutputStream(out)) {
            // 1. 写入 meta.json
            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("filename", filename);
            meta.put("file_size_bytes", fileSizeBytes);
            meta.put("processing_time", processingTime);
            meta.put("status", "success");
            zos.putNextEntry(new ZipEntry("meta.json"));
            zos.write(OBJECT_MAPPER.writeValueAsBytes(meta));
            zos.closeEntry();

            // 2. 写入 <baseName>.md（直接从文件流式复制，不加载到内存）
            Path mdFile = findMarkdownFile(outputDir, inputPath);
            if (mdFile != null && Files.exists(mdFile)) {
                zos.putNextEntry(new ZipEntry(baseName + ".md"));
                Files.copy(mdFile, zos);
                zos.closeEntry();
            }

            // 3. 写入 <baseName>_images/ 下的所有图片（直接流式复制）
            Path imagesDir = outputDir.resolve(baseName + "_images");
            if (Files.isDirectory(imagesDir)) {
                try (Stream<Path> walk = Files.walk(imagesDir)) {
                    walk.filter(p -> !Files.isDirectory(p))
                        .forEach(p -> {
                            String entryName = imagesDir.relativize(p).toString();
                            try {
                                zos.putNextEntry(new ZipEntry(baseName + "_images/" + entryName));
                                Files.copy(p, zos);
                                zos.closeEntry();
                            } catch (IOException e) {
                                log.warn("打包图片失败: {}", p, e);
                            }
                        });
                }
            }
        }

        log.debug("Zip 打包完成: {}.zip", baseName);
    }

    /**
     * 获取文件大小
     */
    public long getFileSize(Path path) {
        try {
            return Files.size(path);
        } catch (IOException e) {
            return 0;
        }
    }

    /**
     * 递归删除目录
     */
    public void cleanupDir(Path dir) {
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

    /**
     * 执行 PDF 解析（固定配置：生成 Markdown + 提取图片）
     */
    private void doProcess(Path inputPath, Path outputDir) throws IOException {
        log.debug("开始解析 PDF: {} -> {}", inputPath, outputDir);

        Config odlConfig = new Config();
        odlConfig.setOutputFolder(outputDir.toString());
        odlConfig.setGenerateMarkdown(true);
        odlConfig.setAddImageToMarkdown(true);

        OpenDataLoaderPDF.processFile(inputPath.toString(), odlConfig);
    }

    /**
     * 查找 ODL 输出的 Markdown 文件（按文件名优先级）
     */
    private Path findMarkdownFile(Path outputDir, Path inputPath) throws IOException {
        String baseName = inputPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");
        Path expectedMd = outputDir.resolve(baseName + ".md");
        if (Files.exists(expectedMd)) {
            return expectedMd;
        }

        return findMarkdownFileInDir(outputDir);
    }

    /**
     * 查找目录中的任意 .md 文件
     */
    private Path findMarkdownFileInDir(Path dir) throws IOException {
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "*.md")) {
            for (Path mdFile : stream) {
                return mdFile;
            }
        }
        try (Stream<Path> walk = Files.walk(dir)) {
            return walk.filter(p -> p.toString().endsWith(".md"))
                    .findFirst()
                    .orElse(null);
        }
    }
}
