FROM node:20-alpine AS frontend-build
WORKDIR /repo/web/frontend
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /repo
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY web/backend/requirements.txt ./web/backend/requirements.txt
RUN pip install --no-cache-dir -r web/backend/requirements.txt
COPY web/backend/ ./web/backend/
COPY course_sot/compact_runtime_spec.yaml course_sot/techniques.yaml course_sot/evaluation_rubric.yaml ./course_sot/
COPY dataset/chunks/B01/B01_ACCEPTED.jsonl ./dataset/chunks/B01/B01_ACCEPTED.jsonl
COPY --from=frontend-build /repo/web/frontend/dist ./web/frontend/dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "/repo/web/backend", "--host", "0.0.0.0", "--port", "8000"]
