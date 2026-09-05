#!/usr/bin/env bash
set -Eeuo pipefail

# Creates a PostgreSQL custom-format dump plus a copy of the bundled MinIO bucket.
# Run on the staging host. It never modifies the source database or bucket.

for command in docker sha256sum; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done

ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="${OUTPUT_DIR:-backups/staging-$STAMP}"
COMPOSE=(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)

mkdir -p "$OUTPUT_DIR/storage"
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_DB | tr -d '\r')"
BUCKET="$("${COMPOSE[@]}" exec -T backend printenv STORAGE_BUCKET | tr -d '\r')"
REMOTE_DIR="/tmp/slrms-backup-$STAMP"

echo "Creating PostgreSQL dump..."
"${COMPOSE[@]}" exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --format=custom --no-owner --no-acl >"$OUTPUT_DIR/postgres.dump"

echo "Copying object storage bucket..."
"${COMPOSE[@]}" exec -T minio mc mirror --overwrite "local/$BUCKET" "$REMOTE_DIR"
MINIO_CONTAINER="$("${COMPOSE[@]}" ps -q minio)"
docker cp "$MINIO_CONTAINER:$REMOTE_DIR/." "$OUTPUT_DIR/storage"
"${COMPOSE[@]}" exec -T minio rm -rf -- "$REMOTE_DIR"

printf 'created_at=%s\ndatabase=%s\nbucket=%s\n' "$STAMP" "$DB_NAME" "$BUCKET" >"$OUTPUT_DIR/metadata.txt"
(
  cd "$OUTPUT_DIR"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
)

echo "Backup created at: $OUTPUT_DIR"
echo "Verify with: (cd '$OUTPUT_DIR' && sha256sum -c SHA256SUMS)"
