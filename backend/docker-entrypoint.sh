#!/bin/sh
set -e

# Apply DB migrations (idempotent — no-op when already at head).
echo "Running database migrations…"
alembic upgrade head

# Serve the API. Trust proxy headers from cloudflared so the OAuth redirect_uri
# and Secure cookies use the real https:// public host.
echo "Starting API…"
exec uvicorn api.main:app \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="*"
