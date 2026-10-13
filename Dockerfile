FROM node:22-slim AS frontend-build
# typia's build-time transform needs a Go toolchain to compile its native plugin.
RUN apt-get update -qq && apt-get install -y -qq golang-go git && rm -rf /var/lib/apt/lists/*
# proxy.golang.org's TLS chain fails to verify on some Docker build networks.
# So fetch the Go module straight from its VCS host instead.
ENV GOPROXY=direct GOSUMDB=off
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.json ./
RUN npm ci
COPY frontend/vite.config.ts frontend/index.html ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim
RUN pip install --no-cache-dir uv

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY backend/app ./app
RUN uv sync --no-dev

COPY data /app/data
COPY --from=frontend-build /frontend/dist /app/dist

ENV DEQ_DB_PATH=/data/deq.db
RUN mkdir -p /data && useradd -u 1000 -m appuser && chown -R appuser /data /app
USER appuser

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
