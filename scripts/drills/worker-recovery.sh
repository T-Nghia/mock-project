#!/usr/bin/env bash
set -Eeuo pipefail

# Run this on the staging host. Required environment variables:
# STAGING_API_URL, SMOKE_EMAIL, SMOKE_PASSWORD.
# Optional: ENV_FILE, PROJECT_NAME, PROCESSING_TIMEOUT_SECONDS.

for command in curl jq docker; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done

: "${STAGING_API_URL:?STAGING_API_URL is required}"
: "${SMOKE_EMAIL:?SMOKE_EMAIL is required}"
: "${SMOKE_PASSWORD:?SMOKE_PASSWORD is required}"

ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
TIMEOUT="${PROCESSING_TIMEOUT_SECONDS:-600}"
API_URL="${STAGING_API_URL%/}"
COMPOSE=(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
WORK_DIR="$(mktemp -d)"
DOCUMENT_ID=""

cleanup() {
  if [[ -n "$DOCUMENT_ID" && -s "$WORK_DIR/token" ]]; then
    curl --fail-with-body --silent --show-error -X DELETE \
      -H "Authorization: Bearer $(<"$WORK_DIR/token")" \
      "$API_URL/documents/$DOCUMENT_ID" >/dev/null || true
  fi
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

jq -n --arg email "$SMOKE_EMAIL" --arg password "$SMOKE_PASSWORD" \
  '{email:$email,password:$password}' >"$WORK_DIR/login.json"
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' --data-binary "@$WORK_DIR/login.json" \
  "$API_URL/auth/login" | jq -er '.access_token' >"$WORK_DIR/token"

MARKER="SLRMS-WORKER-RECOVERY-$(date -u +%Y%m%dT%H%M%SZ)"
for _ in $(seq 1 50000); do printf '%s worker recovery payload\n' "$MARKER"; done >"$WORK_DIR/document.txt"

UPLOAD_RESPONSE="$(curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $(<"$WORK_DIR/token")" \
  -F "file=@$WORK_DIR/document.txt;type=text/plain" -F "title=$MARKER" \
  "$API_URL/documents/upload")"
DOCUMENT_ID="$(jq -er '.id' <<<"$UPLOAD_RESPONSE")"
echo "Created recovery document: $DOCUMENT_ID"

deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  metadata="$(curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer $(<"$WORK_DIR/token")" "$API_URL/documents/$DOCUMENT_ID")"
  status="$(jq -r '.processing_status' <<<"$metadata")"
  if [[ "$status" == "processing" ]]; then break; fi
  if [[ "$status" == "done" ]]; then
    echo "Job completed before the worker could be killed; rerun with a slower provider or larger fixture." >&2
    exit 3
  fi
  if [[ "$status" == "failed" ]]; then jq . <<<"$metadata"; exit 1; fi
  sleep 1
done
[[ "${status:-}" == "processing" ]] || { echo "Timed out waiting for PROCESSING" >&2; exit 1; }

echo "Killing worker while document is processing..."
"${COMPOSE[@]}" kill worker
"${COMPOSE[@]}" up -d worker

while (( SECONDS < deadline )); do
  metadata="$(curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer $(<"$WORK_DIR/token")" "$API_URL/documents/$DOCUMENT_ID")"
  status="$(jq -r '.processing_status' <<<"$metadata")"
  if [[ "$status" == "done" ]]; then break; fi
  if [[ "$status" == "failed" ]]; then jq . <<<"$metadata"; exit 1; fi
  sleep 2
done
[[ "${status:-}" == "done" ]] || { echo "Timed out waiting for recovered job" >&2; exit 1; }

DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_DB | tr -d '\r')"
DUPLICATES="$("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc \
  "SELECT count(*) FROM (SELECT chunk_index FROM document_chunks WHERE document_id = '$DOCUMENT_ID' GROUP BY chunk_index HAVING count(*) > 1) duplicated")"
[[ "$DUPLICATES" == "0" ]] || { echo "Found duplicate chunks: $DUPLICATES" >&2; exit 1; }

echo "PASS: worker recovered the job and no duplicate chunk index was found."
jq '{id,processing_status,processing_attempts,processing_started_at,processing_completed_at}' <<<"$metadata"
