package com.norlandsoft.air.reader.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.multipdf.PageExtractor;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.graphics.PDXObject;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.opendataloader.pdf.api.Config;
import org.opendataloader.pdf.api.OpenDataLoaderPDF;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
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
 * 图片处理策略：
 * - ODL 负责 Markdown 文本生成（含图片占位引用）
 * - PDFBox 负责从 PDF 中直接提取原始嵌入图片（原始分辨率）
 * - ODL 生成的低分辨率渲染图片被替换为原始分辨率图片
 *
 * 大文档处理：
 * - 超过 CHUNK_SIZE 页的 PDF 自动分片处理
 * - 使用 PDFBox PageExtractor 拆分，每片独立处理
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
     * 将 PDF 文件解析为 Markdown + 图片，返回输出目录
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

            int totalPages = getPdfPageCount(pdfPath);
            log.info("PDF 文件: {}, 总页数: {}", pdfPath.getFileName(), totalPages);

            if (totalPages <= CHUNK_SIZE) {
                doProcess(pdfPath, outputDir);
                // 用 PDFBox 提取原始分辨率图片替换 ODL 的低分辨率版本
                replaceWithOriginalImages(pdfPath, outputDir);
            } else {
                processInChunks(pdfPath, outputDir, totalPages);
            }

            log.info("PDF 解析完成: file={}, pages={}", pdfPath.getFileName(), totalPages);
            return ExtractResult.success(outputDir);
        } catch (Exception e) {
            log.error("PDF 解析失败: file={}, error={}", pdfPath.getFileName(), e.getMessage(), e);
            cleanupDir(outputDir);
            return ExtractResult.failure("PDF 解析失败: " + e.getMessage());
        }
    }

    /**
     * 用 PDFBox 从 PDF 中提取原始嵌入图片，替换 ODL 生成的低分辨率渲染图片
     *
     * ODL 通过渲染页面生成图片，分辨率约为原始的 40%。
     * 此方法直接从 PDF 页面资源中提取原始嵌入图片，保持原始分辨率和质量。
     *
     * 遍历每个页面的 XObject 资源，按出现顺序命名 imageFileN.png，
     * 与 ODL 的命名规则一致，确保 Markdown 中的引用路径仍然有效。
     */
    private void replaceWithOriginalImages(Path pdfPath, Path outputDir) throws IOException {
        Path imagesDir = findImagesDir(outputDir);
        if (imagesDir == null) {
            log.debug("未找到 ODL 图片目录，跳过原始图片替换");
            return;
        }

        int replaced = 0;
        try (PDDocument doc = Loader.loadPDF(pdfPath.toFile())) {
            for (PDPage page : doc.getPages()) {
                PDResources resources = page.getResources();
                if (resources == null) continue;

                Iterable<COSName> xObjectNames = resources.getXObjectNames();
                for (COSName name : xObjectNames) {
                    try {
                        PDXObject xobject = resources.getXObject(name);
                        if (xobject instanceof PDImageXObject) {
                            PDImageXObject image = (PDImageXObject) xobject;
                            replaced++;

                            String filename = "imageFile" + replaced + ".png";
                            Path outputFile = imagesDir.resolve(filename);

                            ImageIO.write(image.getImage(), "PNG", outputFile.toFile());
                        }
                    } catch (IOException e) {
                        log.debug("提取图片 {} 失败: {}", name.getName(), e.getMessage());
                    }
                }
            }
        }

        log.info("原始图片替换完成: {} 张", replaced);
    }

    /**
     * 在输出目录中查找 ODL 生成的图片目录（*_images/）
     */
    private Path findImagesDir(Path outputDir) throws IOException {
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(outputDir)) {
            for (Path entry : stream) {
                if (Files.isDirectory(entry) && entry.getFileName().toString().endsWith("_images")) {
                    return entry;
                }
            }
        }
        return null;
    }

    /**
     * 获取 PDF 页数
     */
    private int getPdfPageCount(Path pdfPath) throws IOException {
        try (PDDocument doc = Loader.loadPDF(pdfPath.toFile())) {
            return doc.getNumberOfPages();
        }
    }

    /**
     * 分片处理大 PDF
     */
    private void processInChunks(Path pdfPath, Path outputDir, int totalPages) throws IOException {
        log.info("分片处理: {} 页, 每片 {} 页, 共 {} 片", totalPages, CHUNK_SIZE,
                (totalPages + CHUNK_SIZE - 1) / CHUNK_SIZE);

        String baseName = pdfPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");
        StringBuilder mergedMarkdown = new StringBuilder();

        try (PDDocument sourceDoc = Loader.loadPDF(pdfPath.toFile())) {
            int totalChunks = (totalPages + CHUNK_SIZE - 1) / CHUNK_SIZE;
            int chunkIndex = 0;

            for (int startPage = 1; startPage <= totalPages; startPage += CHUNK_SIZE) {
                int endPage = Math.min(startPage + CHUNK_SIZE - 1, totalPages);
                chunkIndex++;

                log.info("处理分片 {}/{}: 页 {}-{}", chunkIndex, totalChunks, startPage, endPage);

                // 1. 提取子文档
                PageExtractor extractor = new PageExtractor(sourceDoc, startPage, endPage);
                Path chunkFile = outputDir.resolve("chunk_" + chunkIndex + ".pdf");

                try (PDDocument chunkDoc = extractor.extract()) {
                    chunkDoc.save(chunkFile.toFile());
                }

                // 2. ODL 处理
                Path chunkOutputDir = outputDir.resolve("chunk_" + chunkIndex + "_out");
                Files.createDirectories(chunkOutputDir);

                try {
                    doProcess(chunkFile, chunkOutputDir);
                    // 用 PDFBox 从分片 PDF 中提取原始图片
                    replaceWithOriginalImages(chunkFile, chunkOutputDir);
                } catch (Exception e) {
                    log.warn("分片 {}/{} 处理失败: {}", chunkIndex, totalChunks, e.getMessage());
                }

                // 3. 读取 markdown 并加前缀
                Path chunkMd = findMarkdownFileInDir(chunkOutputDir);
                if (chunkMd != null && Files.exists(chunkMd)) {
                    String content = Files.readString(chunkMd, StandardCharsets.UTF_8);
                    if (!content.isEmpty()) {
                        if (mergedMarkdown.length() > 0) {
                            mergedMarkdown.append("\n\n---\n\n");
                        }
                        mergedMarkdown.append(prefixImageRefs(content, chunkIndex));
                    }
                }

                // 4. 收集图片
                collectChunkImages(chunkOutputDir, outputDir, baseName, chunkIndex);

                // 5. 清理
                Files.deleteIfExists(chunkFile);
                cleanupDir(chunkOutputDir);
            }
        }

        Path mergedMdFile = outputDir.resolve(baseName + ".md");
        Files.writeString(mergedMdFile, mergedMarkdown.toString(), StandardCharsets.UTF_8);
        log.info("分片合并完成: {} 字符, {} 图片", mergedMarkdown.length(),
                countImages(outputDir.resolve(baseName + "_images")));
    }

    private String prefixImageRefs(String markdown, int chunkIndex) {
        String prefix = "chunk_" + chunkIndex + "_";
        return markdown.replaceAll(
            "!\\[([^\\]]*)\\]\\(([^)]*_images/)([^/)]+)\\)",
            "![$1]($2" + prefix + "$3)"
        );
    }

    private void collectChunkImages(Path chunkOutputDir, Path outputDir, String baseName, int chunkIndex) throws IOException {
        Path mainImagesDir = outputDir.resolve(baseName + "_images");

        try (Stream<Path> walk = Files.walk(chunkOutputDir)) {
            walk.filter(p -> Files.isDirectory(p) && p.getFileName().toString().endsWith("_images"))
                .findFirst()
                .ifPresent(imagesDir -> {
                    try {
                        Files.createDirectories(mainImagesDir);
                        try (Stream<Path> imgFiles = Files.list(imagesDir)) {
                            imgFiles.filter(p -> !Files.isDirectory(p))
                                .forEach(imgFile -> {
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

    private int countImages(Path imagesDir) {
        if (!Files.isDirectory(imagesDir)) return 0;
        try (Stream<Path> list = Files.list(imagesDir)) {
            return (int) list.filter(p -> !Files.isDirectory(p)).count();
        } catch (IOException e) {
            return 0;
        }
    }

    /**
     * 将输出目录流式打包为 zip
     */
    public void packageAsZip(OutputStream out, Path outputDir, Path inputPath,
                             String filename, long fileSizeBytes, double processingTime) throws IOException {
        String baseName = inputPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");

        try (ZipOutputStream zos = new ZipOutputStream(out)) {
            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("filename", filename);
            meta.put("file_size_bytes", fileSizeBytes);
            meta.put("processing_time", processingTime);
            meta.put("status", "success");
            zos.putNextEntry(new ZipEntry("meta.json"));
            zos.write(OBJECT_MAPPER.writeValueAsBytes(meta));
            zos.closeEntry();

            Path mdFile = findMarkdownFile(outputDir, inputPath);
            if (mdFile != null && Files.exists(mdFile)) {
                zos.putNextEntry(new ZipEntry(baseName + ".md"));
                Files.copy(mdFile, zos);
                zos.closeEntry();
            }

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
    }

    public long getFileSize(Path path) {
        try { return Files.size(path); } catch (IOException e) { return 0; }
    }

    public void cleanupDir(Path dir) {
        if (dir == null || !Files.exists(dir)) return;
        try (Stream<Path> walk = Files.walk(dir)) {
            walk.sorted(Comparator.reverseOrder())
                    .forEach(p -> {
                        try { Files.deleteIfExists(p); } catch (IOException e) { /* ignore */ }
                    });
        } catch (IOException e) {
            log.warn("清理临时目录失败: {}", dir, e);
        }
    }

    private void doProcess(Path inputPath, Path outputDir) throws IOException {
        Config odlConfig = new Config();
        odlConfig.setOutputFolder(outputDir.toString());
        odlConfig.setGenerateMarkdown(true);
        odlConfig.setAddImageToMarkdown(true);
        OpenDataLoaderPDF.processFile(inputPath.toString(), odlConfig);
    }

    private Path findMarkdownFile(Path outputDir, Path inputPath) throws IOException {
        String baseName = inputPath.getFileName().toString().replaceAll("\\.(?i)pdf$", "");
        Path expectedMd = outputDir.resolve(baseName + ".md");
        if (Files.exists(expectedMd)) return expectedMd;
        return findMarkdownFileInDir(outputDir);
    }

    private Path findMarkdownFileInDir(Path dir) throws IOException {
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "*.md")) {
            for (Path mdFile : stream) return mdFile;
        }
        try (Stream<Path> walk = Files.walk(dir)) {
            return walk.filter(p -> p.toString().endsWith(".md")).findFirst().orElse(null);
        }
    }
}
