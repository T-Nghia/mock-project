#!/usr/bin/env bash
set -Eeuo pipefail
for command in docker sha256sum python3; do
  command -v "$command" >/dev/null || exit 2
done
: "${BACKUP_DIR:?BACKUP_DIR is required}"
[[ -f "$BACKUP_DIR/postgres.dump" && -f "$BACKUP_DIR/SHA256SUMS" ]] || exit 2
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
TOKEN="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
VERIFY_DB="slrms_restore_verify_$TOKEN"
VERIFY_BUCKET="slrms-restore-verify-$TOKEN"
COMPOSE=(docker compose --profile cleanup -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER | tr -d '\r')"
"${COMPOSE[@]}" exec -T db createdb -U "$DB_USER" "$VERIFY_DB"
"${COMPOSE[@]}" exec -T db pg_restore -U "$DB_USER" -d "$VERIFY_DB" --no-owner --no-acl < "$BACKUP_DIR/postgres.dump"
"${COMPOSE[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" \
  -e DOCUMENT_DELETE_ENABLED=false -e DOCUMENT_MUTATIONS_ENABLED=false -e CLEANUP_ENABLED=false \
  -v "$BACKUP_DIR:/backup:ro" backend python -m app.storage_backup restore --directory /backup/storage --bucket "$VERIFY_BUCKET"
"${COMPOSE[@]}" run --rm --no-deps -T \
  -e DOCUMENT_DELETE_ENABLED=false -e DOCUMENT_MUTATIONS_ENABLED=false -e CLEANUP_ENABLED=false \
  -e STORAGE_BUCKET="$VERIFY_BUCKET" -e VERIFY_DATABASE="$VERIFY_DB" backend python -c '
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.storage_backup import verify_live_references
engine = create_engine(make_url(settings.DATABASE_URL).set(database=os.environ["VERIFY_DATABASE"]))
try:
    print(verify_live_references(sessionmaker(bind=engine)))
finally:
    engine.dispose()
'
echo "Verification targets retained: database=$VERIFY_DB bucket=$VERIFY_BUCKET"
echo 'Cleanup stays disabled. Audit queue/leases and target mismatch before any activation. Never remap automatically.'
