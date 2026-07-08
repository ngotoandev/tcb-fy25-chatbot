# ---- frontend build ----
FROM node:22-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY data/artifacts ./data/artifacts
COPY --from=fe /fe/dist ./static
ENV ARTIFACTS_DIR=/srv/data/artifacts STATIC_DIR=/srv/static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
