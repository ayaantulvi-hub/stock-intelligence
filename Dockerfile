FROM node:22-slim AS dashboard
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/ ./
RUN uv sync --no-dev --frozen
COPY --from=dashboard /app/dist /app/dashboard
ENV APP_ENV=production STATIC_DIR=/app/dashboard
CMD ["sh", "-c", "exec .venv/bin/uvicorn stockintel.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
