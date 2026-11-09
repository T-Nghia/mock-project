#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Approved maintenance window required. Leave writers stopped on success/error.
# Never infer quiescence from lease expiry; no shell/mc is needed in MinIO.
for command in docker sha256sum git python3; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done
: "${BACKUP_QUIESCENCE_EVIDENCE:?Ops target-bound storage drain/delete-fence evidence is required}"
[[ -f "$BACKUP_QUIESCENCE_EVIDENCE" ]] || exit 2
ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="${OUTPUT_DIR:-backups/staging-$STAMP}"
REVISION="$(git rev-parse HEAD)"
[[ ! -e "$OUTPUT_DIR" ]] || { echo 'Refusing to overwrite an existing backup' >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
COMPOSE=(docker compose --profile cleanup -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
"${COMPOSE[@]}" stop --timeout 180 caddy frontend backend worker cleanup
for service in caddy frontend backend worker cleanup; do
  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    state="$(docker inspect --format '{{.State.Running}} {{.State.ExitCode}}' "$container")"
    [[ "$state" == 'false 0' ]] || { echo 'Unclean writer shutdown: keep gates closed and investigate' >&2; exit 1; }
  done < <("${COMPOSE[@]}" ps --all --quiet "$service")
done
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_DB | tr -d '\r')"
CONNECTIONS="$("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")"
[[ "$CONNECTIONS" == 0 ]] || { echo 'Unknown database clients remain; backup refused' >&2; exit 1; }
cp -- "$BACKUP_QUIESCENCE_EVIDENCE" "$OUTPUT_DIR/quiescence.json"
"${COMPOSE[@]}" exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-acl > "$OUTPUT_DIR/postgres.dump"
"${COMPOSE[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" \
  -e DOCUMENT_DELETE_ENABLED=false -e DOCUMENT_MUTATIONS_ENABLED=false -e CLEANUP_ENABLED=false \
  -v "$OUTPUT_DIR:/backup" backend python -m app.storage_backup export \
  --directory /backup/storage --revision "$REVISION" --quiescence-evidence /backup/quiescence.json
printf 'created_at=%s\nrevision=%s\ndatabase=%s\nwriters=stopped\n' "$STAMP" "$REVISION" "$DB_NAME" > "$OUTPUT_DIR/metadata.txt"
(cd "$OUTPUT_DIR" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
echo 'Backup complete. Writers remain stopped. Follow the approved resume order in the runbook.'
