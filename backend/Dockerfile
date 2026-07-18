FROM python:3.12-slim

# Faster, cleaner Python in containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so they cache across code changes
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App code (tests/evals excluded via .dockerignore)
COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Entrypoint runs Alembic migrations, then serves the API. --proxy-headers +
# --forwarded-allow-ips="*" make uvicorn trust X-Forwarded-Proto/Host from
# cloudflared (same docker network) so request.url_for builds the public https
# URL for the Google OAuth redirect.
ENTRYPOINT ["./docker-entrypoint.sh"]
