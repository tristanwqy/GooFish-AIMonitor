# 基础镜像可用 ARG 覆盖到在区镜像源: --build-arg PYTHON_IMAGE=<your-mirror>/python:3.12-slim
# (不加 `# syntax=` 指令, 避免 CN 网络拉 docker.io frontend 超时)
ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:20-slim

# ---------- 前端构建 ----------
FROM ${NODE_IMAGE} AS fe
WORKDIR /fe
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npx vite build --outDir dist --emptyOutDir

# ---------- 应用 ----------
FROM ${PYTHON_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    XIANYU_DATA_DIR=/app/data \
    PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
ARG APT_MIRROR=mirrors.tencent.com
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true

WORKDIR /app
# 依赖层: 只依赖 pyproject。先放最小包骨架让 `-e .` 能装, 再装依赖 + Chromium。
# 改 app 源码不会让这层失效(Chromium ~300MB 不必每次重下)。
COPY pyproject.toml ./
RUN mkdir -p src/xianyu_crawler && touch src/xianyu_crawler/__init__.py \
    && pip install \
        --index-url https://mirrors.tencent.com/pypi/simple/ --trusted-host mirrors.tencent.com \
        --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn \
        -e . \
    && playwright install --with-deps chromium

# 应用层: 真实源码 + 前端产物。改这里只重跑这两步(秒级), 不动上面的 Chromium 层。
COPY src ./src
COPY --from=fe /fe/dist ./src/xianyu_crawler/web/static

EXPOSE 8000
CMD ["python", "-m", "xianyu_crawler.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
