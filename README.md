# AirFileReader

OpenDataLoader 服务 — 从文档中提取内容并转换为 Markdown 格式，通过 REST API 对外提供文档内容读取服务。

## 功能

- **文档提取**：支持 PDF、Word、PowerPoint、Excel、HTML、TXT、Markdown、图片等多种格式
- **Markdown 输出**：统一将文档内容转换为 Markdown 格式返回
- **REST API**：标准的 HTTP 接口，方便第三方系统集成
- **容器化部署**：提供 Dockerfile 和 docker-compose，一键构建和部署

## 快速开始

### 本地运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看 API 文档。

### Docker 部署

```bash
# 方式一：使用构建脚本
bash scripts/build.sh

# 方式二：使用 docker compose
docker compose up -d

# 方式三：手动构建
docker build -t airfilereader:latest .
docker run -p 8000:8000 airfilereader:latest
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 |
| `POST` | `/api/v1/documents/extract` | 上传文档，返回 Markdown |
| `GET` | `/api/v1/documents/{doc_id}` | 获取已存储的文档 |

### 示例

```bash
# 提取 PDF 内容
curl -X POST http://localhost:8000/api/v1/documents/extract \
  -F "file=@document.pdf"

# 提取并存储
curl -X POST "http://localhost:8000/api/v1/documents/extract?store=true" \
  -F "file=@document.pdf"
```

## 项目结构

```
AirFileReader/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── open_data_loader.py  # 文档提取核心服务
│   ├── models.py            # 数据模型
│   └── routers/
│       └── document.py      # API 路由
├── scripts/
│   └── build.sh             # 容器构建脚本
├── tests/
│   └── test_document.py     # 单元测试
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
