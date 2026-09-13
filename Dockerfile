FROM node:22-bookworm-slim AS web
WORKDIR /app/mobile
ENV EXPO_NO_DOTENV=1 CI=1 EXPO_NO_TELEMETRY=1
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci
COPY mobile/ ./
RUN npm run typecheck && npm run build:web

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production \
    WEB_DIST_DIR=/app/web ALLOW_DEV_BEARER=false
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/
COPY backend/migrations/ ./migrations/
COPY backend/alembic.ini ./
COPY --from=web /app/mobile/dist/ /app/web/
RUN useradd --uid 10001 --create-home moneyapp
USER moneyapp
EXPOSE 10000
CMD ["python", "-m", "app.start_server"]
