FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY ocr_beans/ ./ocr_beans/

RUN pip install --no-cache-dir .

ENV TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 8080

# API web + REST (UI em http://localhost:8080/)
# Para rodar como MCP server remoto: docker run ... python -m ocr_beans.mcp_server --remote
CMD ["python", "-m", "ocr_beans.api", "--host", "0.0.0.0", "--port", "8080"]
