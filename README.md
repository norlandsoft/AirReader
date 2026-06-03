# AirFileReader

PDF 文档内容读取服务 — 基于 OpenDataLoader 将 PDF 转换为 Markdown，通过 Docling 风格的 REST API 对外提供服务。

## 功能

- **PDF 提取**：使用 OpenDataLoader 进程内解析，将 PDF 内容转换为 Markdown
- **Docling 风格 API**：对齐 Docling-serve 的端点路径和响应结构
- **容器化部署**：提供 Dockerfile 和 docker-compose，一键构建和部署

## 快速开始

### Docker 部署

```bash
# 使用 docker compose
docker compose up -d

# 或手动构建
docker build -t air-filereader:latest .
docker run -p 9103:8000 air-filereader:latest
```

### 本地运行

```bash
mvn spring-boot:run
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/v1alpha/convert/file` | 上传 PDF，返回 Markdown |

### 示例

```bash
# 健康检查
curl http://localhost:9103/health

# 提取 PDF 内容为 Markdown
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf"

# 提取为纯文本
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf" \
  -F "to_formats=text"

# 启用 HTML 标签和图片引用
curl -X POST http://localhost:9103/v1alpha/convert/file \
  -F "files=@document.pdf" \
  -F "markdown_with_html=true" \
  -F "markdown_with_images=true"
```

## 项目结构

```
AirFileReader/
├── src/main/java/com/airfilereader/
│   ├── Application.java                  -- Spring Boot 启动类
│   ├── controller/
│   │   └── ConvertController.java        -- REST 端点
│   ├── model/
│   │   └── ConvertResponse.java          -- Docling 风格响应模型
│   └── service/
│       ├── OpenDataLoaderService.java    -- ODL 核心解析服务
│       ├── ExtractConfig.java            -- 解析配置
│       └── ExtractResult.java            -- 解析结果
├── Dockerfile
├── docker-compose.yml
└── pom.xml
```
