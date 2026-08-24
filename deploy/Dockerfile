# 私有化部署镜像。ROADMAP 阶段 G。
#
# 两阶段构建：编译期装 build 工具，运行期不装。理由不是镜像大小，而是攻击面——
# 一个能拉取并编译任意包的运行时容器，是从「一次代码执行」到「持久化后门」最短的路径。
#
# 镜像**不内置任何凭据、也不预置数据库**。平台库连接串、管理员口令、模型密钥
# 全部由运行时注入。镜像里带一份 SQLite 会让所有部署共用同一份初始数据，
# 而那份数据保存的是数据源连接串。

FROM python:3.11-slim AS build

WORKDIR /src
# 只复制构建所需，避免 .git 与本地数据文件进入构建上下文。
COPY pyproject.toml README.md LICENSE ./
COPY backend ./backend

RUN python -m pip install --no-cache-dir --upgrade pip build \
 && python -m build --wheel --outdir /dist


FROM python:3.11-slim AS runtime

# 非 root 运行。平台库保存全部数据源连接串，等同凭据存储——
# 以 root 运行意味着一次容器逃逸即可拿到它们。
RUN useradd --create-home --uid 10001 aletheia

# `[all]` 装上 PostgreSQL／MySQL 驱动与文档解析。只需内核的部署可以改为不带 extra，
# 内核本身零第三方依赖。
COPY --from=build /dist/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl[all] \
 && rm -rf /tmp/*.whl

# 状态目录。挂卷到这里，容器本身保持无状态。
ENV ONTOLOGY_DATA_DIR=/var/lib/aletheia
RUN mkdir -p /var/lib/aletheia && chown aletheia:aletheia /var/lib/aletheia

USER aletheia
WORKDIR /var/lib/aletheia

# 默认监听全部网卡：容器内没有别的选择。正因如此，
# `aletheia serve` 在非本机监听时会**强制跑部署前自检并在阻断项存在时拒绝启动**——
# 否则一个残留的 ONTOLOGY_AUTH_DISABLED=1 会让整套 API 免鉴权暴露。
EXPOSE 8000

# 健康检查打的是 /health，它在 PUBLIC_PATHS 里，因此无需令牌。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["aletheia"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
