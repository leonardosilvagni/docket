# One small image for both calendar services (Radicale server + the sync script).
FROM python:3.13-alpine
RUN apk add --no-cache tzdata \
 && pip install --no-cache-dir "radicale>=3,<4"
ENV PYTHONDONTWRITEBYTECODE=1
