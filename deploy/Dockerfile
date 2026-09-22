# 多阶段构建：先构建前端，再构建后端
# 最终镜像只包含运行时依赖，体积最小化

# ---- 阶段 1: 构建前端 ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
# The Vite compiler and TypeScript are devDependencies but are required in this build
# stage; only the final Python image is runtime-only.
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- 阶段 2: 构建后端 ----
FROM python:3.11-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY backend ./backend
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[all]"

# ---- 阶段 3: 运行时镜像 ----
FROM python:3.11-slim AS runtime
WORKDIR /app

# 创建非 root 用户。默认工作目录放在状态卷中，SQLite 评估模式不会把数据写进
# 容器可写层；PostgreSQL 部署也会复用这个目录保存上传文件和备份。
RUN groupadd -r aletheia \
    && useradd -r -g aletheia -d /var/lib/aletheia -s /sbin/nologin aletheia \
    && mkdir -p /var/lib/aletheia \
    && chown aletheia:aletheia /var/lib/aletheia

# 安装已构建的后端 wheel，避免 editable 安装把源码路径带进运行镜像。
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# 复制前端构建产物
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

USER aletheia

# 状态目录。即使不使用 compose 的 PostgreSQL，单容器 SQLite 评估也必须持久化。
WORKDIR /var/lib/aletheia
ENV ONTOLOGY_DATA_DIR=/var/lib/aletheia

# 前端构建产物不在 Python wheel 中，显式告诉运行时它的位置。
ENV ALETHEIA_FRONTEND_DIST=/app/frontend/dist
ENV PYTHONUNBUFFERED=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 暴露端口
EXPOSE 8000

ENV ONTOLOGY_AUTH_DISABLED=0

# 通过 CLI 启动而不是直接调用 uvicorn：非本机监听时必须经过部署前自检，避免
# 把残留的免鉴权开关或不安全 CORS 配置直接暴露到网络。
ENTRYPOINT ["aletheia"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
