#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[ERROR] Thiếu biến môi trường DATABASE_URL. Hãy cấu hình chuỗi kết nối MySQL (Aiven) trên Render." >&2
  exit 1
fi

cd /app/back-end

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[DEPLOY] Chạy Alembic migration (alembic upgrade head)..."
  python -m alembic upgrade head
fi

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "[DEPLOY] Nạp dữ liệu mẫu (app.db.seed)..."
  python -m app.db.seed
  if [ -n "${SEED_ADMIN_EMAIL:-}" ] && [ -n "${SEED_ADMIN_PASSWORD:-}" ]; then
    echo "[DEPLOY] Tạo/kiểm tra tài khoản ADMIN riêng..."
    python -m app.db.seed --admin
  fi
fi

echo "[DEPLOY] Khởi động FastAPI backend trên 127.0.0.1:8000..."
python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips="*" &
BACKEND_PID=$!

cleanup() {
  echo "[DEPLOY] Đang dừng các tiến trình..."
  kill -TERM "$BACKEND_PID" 2>/dev/null || true
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill -TERM "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup TERM INT

# Đợi backend sẵn sàng trước khi mở frontend proxy (tối đa 30 giây)
READY=0
for i in $(seq 1 30); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[ERROR] Backend FastAPI đã dừng ngoài ý muốn khi khởi động." >&2
    wait "$BACKEND_PID"
    exit 1
  fi
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "[ERROR] Backend không phản hồi /api/health sau 30 giây." >&2
  cleanup
  exit 1
fi

export HOST="0.0.0.0"
export PORT="${PORT:-4173}"
export BACKEND_URL="http://127.0.0.1:8000"

echo "[DEPLOY] Khởi động Frontend proxy trên ${HOST}:${PORT} -> ${BACKEND_URL}..."
cd /app/front-end
node serve.cjs &
FRONTEND_PID=$!

# Giữ container sống chừng nào cả 2 tiến trình còn chạy
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 2
done

echo "[ERROR] Một tiến trình (backend hoặc frontend) đã thoát." >&2
cleanup
exit 1
