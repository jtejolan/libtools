#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ] && [ -n "${RAILWAY_ENVIRONMENT:-}" ]; then
    if [ -z "${RAILWAY_VOLUME_MOUNT_PATH:-}" ]; then
        echo "A Railway volume is required when DATABASE_URL is not configured." >&2
        echo "Attach a volume to this service at /data and redeploy." >&2
        exit 1
    fi

    database_path="${RAILWAY_VOLUME_MOUNT_PATH}/librarytools.db"
    if [ ! -f "${database_path}" ]; then
        seed_database="${LIBTOOLS_SEED_DATABASE:-/app/backend/librarytools.db}"
        cp "${seed_database}" "${database_path}"
    fi
    export DATABASE_URL="sqlite:///${database_path}"
fi

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips="*"
