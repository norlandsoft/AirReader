package com.norlandsoft.air.reader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * AirFileReader 启动类
 *
 * PDF 文档内容读取服务，基于 OpenDataLoader 将 PDF 转换为 Markdown。
 * 对外提供 Docling 风格的 REST API。
 *
 * @author ChaiMingXu
 * @since 2026-06-03
 */
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
