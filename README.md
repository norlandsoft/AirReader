# AirParser

PDF to Markdown conversion service powered by PyMuPDF + pdfplumber.

Extracts text, images (original resolution), and tables from PDF files,
returning a zip package with Markdown and image assets.

## Features

- Text extraction with layout preservation
- Image extraction at original resolution (zero loss)
- Table extraction to Markdown table syntax
- Header/footer image filtering
- Fully compatible API (zip response format)

## Quick Start

### Local

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 9103
```

### Docker

```bash
# 1. 构建镜像
docker build -t air-parser:3.0.0 .

# 2. 启动服务
docker compose up -d
```

## API

### Health Check

```bash
curl http://localhost:9103/api/v1/health
# {"status":"healthy","version":"3.0.0"}
```

### Convert PDF

```bash
curl -X POST http://localhost:9103/api/v1/convert/file \
  -F "files=@document.pdf" \
  -o document.zip
```

Response is a zip containing:
- `meta.json` — status and metadata
- `{name}.md` — extracted Markdown
- `{name}_images/` — extracted images (original resolution)

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web Framework | FastAPI + uvicorn |
| PDF Extraction | PyMuPDF (fitz) |
| Table Extraction | pdfplumber |
| Runtime | Python 3.12+ |

## License

Proprietary
