# ═════════════════════════════════════════════════════════════
# Stage 1: Build frontend (Vite + React)
# ═════════════════════════════════════════════════════════════
FROM node:22 AS frontend

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ═════════════════════════════════════════════════════════════
# Stage 2: Build Python backend (uv-powered)
# ═════════════════════════════════════════════════════════════
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Dependencies first (cached layer)
COPY pyproject.toml uv.lock .env.example ./
RUN uv sync --no-dev --no-install-project

# Application code
COPY app/ ./app/
COPY test/ ./test/

# Install project itself
RUN uv sync --no-dev

# Copy built frontend static files
COPY --from=frontend /app/frontend/dist ./static

# Make static dir import-friendly
ENV FRONTEND_STATIC_DIR=/app/static
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
