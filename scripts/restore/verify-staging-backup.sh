#!/usr/bin/env bash
set -Eeuo pipefail

# Restores into a newly-created verification database and MinIO bucket. The live
# staging database/bucket are never overwritten. Set CLEANUP_VERIFY=1 to remove
# only the generated verification targets after successful validation.

for command in docker sha256sum; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done

: "${BACKUP_DIR:?BACKUP_DIR must point to a staging backup directory}"
[[ -f "$BACKUP_DIR/postgres.dump" && -f "$BACKUP_DIR/SHA256SUMS" ]] || {
  echo "Backup is incomplete: postgres.dump or SHA256SUMS is missing" >&2; exit 2;
}

(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)

ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
STAMP="$(date -u +%Y%m%d%H%M%S)"
VERIFY_DB="slrms_restore_verify_$STAMP"
VERIFY_BUCKET="slrms-restore-verify-$STAMP"
REMOTE_DIR="/tmp/slrms-restore-$STAMP"
COMPOSE=(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER | tr -d '\r')"

echo "Creating isolated verification database: $VERIFY_DB"
"${COMPOSE[@]}" exec -T db createdb -U "$DB_USER" "$VERIFY_DB"
"${COMPOSE[@]}" exec -T db pg_restore -U "$DB_USER" -d "$VERIFY_DB" \
  --no-owner --no-acl <"$BACKUP_DIR/postgres.dump"

MINIO_CONTAINER="$("${COMPOSE[@]}" ps -q minio)"
docker cp "$BACKUP_DIR/storage/." "$MINIO_CONTAINER:$REMOTE_DIR"
"${COMPOSE[@]}" exec -T minio mc mb --ignore-existing "local/$VERIFY_BUCKET"
"${COMPOSE[@]}" exec -T minio mc mirror --overwrite "$REMOTE_DIR" "local/$VERIFY_BUCKET"

DOCUMENTS="$("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$VERIFY_DB" -Atc 'SELECT count(*) FROM documents')"
CHUNKS="$("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$VERIFY_DB" -Atc 'SELECT count(*) FROM document_chunks')"
MISSING=0
while IFS= read -r key; do
  [[ -z "$key" ]] && continue
  if ! "${COMPOSE[@]}" exec -T minio mc stat "local/$VERIFY_BUCKET/$key" >/dev/null 2>&1; then
    echo "Missing restored object: $key" >&2
    MISSING=$((MISSING + 1))
  fi
done < <("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$VERIFY_DB" -Atc 'SELECT file_path FROM documents ORDER BY file_path')

[[ "$MISSING" == "0" ]] || { echo "Restore verification failed: $MISSING objects missing" >&2; exit 1; }
echo "PASS: restored database and object references are consistent. documents=$DOCUMENTS chunks=$CHUNKS"
echo "Verification database: $VERIFY_DB"
echo "Verification bucket: $VERIFY_BUCKET"

if [[ "${CLEANUP_VERIFY:-0}" == "1" ]]; then
  echo "Removing generated verification targets..."
  "${COMPOSE[@]}" exec -T db dropdb -U "$DB_USER" "$VERIFY_DB"
  "${COMPOSE[@]}" exec -T minio mc rb --force "local/$VERIFY_BUCKET"
  "${COMPOSE[@]}" exec -T minio rm -rf -- "$REMOTE_DIR"
else
  echo "Targets were retained for inspection. Set CLEANUP_VERIFY=1 on the next drill to clean automatically."
fi
