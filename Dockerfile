FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    APP_ENV=demo

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/approval_loop /app/approval_loop
COPY --from=frontend-builder /app/frontend/dist /app/static

EXPOSE 8080

CMD ["uvicorn", "approval_loop.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
