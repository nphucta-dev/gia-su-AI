# Gia Sư AI - Single-container image for Render (FastAPI backend + Node static/proxy frontend)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Cài Node.js (chạy front-end/serve.cjs) và ca-certificates (TLS tới Aiven MySQL & LLM API)
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Cài dependencies Python trước để tận dụng Docker layer cache
COPY back-end/requirements.txt /app/back-end/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/back-end/requirements.txt

# Copy mã nguồn backend, frontend và script khởi động
COPY back-end /app/back-end
COPY front-end /app/front-end
COPY deploy/start.sh /app/deploy/start.sh

# Bảo đảm LF line endings và quyền thực thi (an toàn khi push từ Windows)
RUN sed -i 's/\r$//' /app/deploy/start.sh \
    && chmod +x /app/deploy/start.sh \
    && mkdir -p /app/back-end/storage/documents

EXPOSE 4173

CMD ["/app/deploy/start.sh"]
