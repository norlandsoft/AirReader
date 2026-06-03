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
