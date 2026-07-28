# Multi-stage: builds frontend inside Docker (works on Hostinger from GitHub;
# no need to commit frontend/dist or build on your laptop).

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY premarket /app/premarket
COPY backend /app/backend
COPY --from=frontend /ui/dist /app/frontend/dist

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/premarket.db

RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
