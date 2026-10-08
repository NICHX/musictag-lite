# syntax=docker/dockerfile:1

# ============================================================
# 阶段 1：构建前端静态资源（Node）
# ============================================================
FROM node:24-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ============================================================
# 阶段 2：Python 运行时（FastAPI 同时托管 /api 与前端静态资源）
# 核心功能不依赖 ffmpeg
# ============================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    MUSIC_ROOT=/music \
    FRONTEND_DIST=/app/frontend/dist \
    SERVE_FRONTEND=true \
    ENVIRONMENT=production

WORKDIR /app

# 可选外部工具：Chromaprint 的 fpcalc（F14 指纹识别用；核心功能不依赖它）
RUN apt-get update \
    && apt-get install -y --no-install-recommends libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

# 安装后端（先拷依赖描述以利用构建缓存）
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/alembic.ini
RUN pip install --no-cache-dir ./backend

# 前端构建产物
COPY --from=frontend /build/frontend/dist ./frontend/dist

# 非 root 运行
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app
USER appuser

VOLUME ["/data", "/music"]
EXPOSE 8000

WORKDIR /app/backend

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

# 启动：先跑数据库迁移，再启动服务
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
