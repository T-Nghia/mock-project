#!/usr/bin/env bash
set -Eeuo pipefail

# Run this on the staging host. Required environment variables:
# STAGING_API_URL, SMOKE_EMAIL, SMOKE_PASSWORD.
# Optional: ENV_FILE, PROJECT_NAME, PROCESSING_TIMEOUT_SECONDS,
# RECOVERY_FIXTURE_LINES.

for command in curl jq docker; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done

: "${STAGING_API_URL:?STAGING_API_URL is required}"
: "${SMOKE_EMAIL:?SMOKE_EMAIL is required}"
: "${SMOKE_PASSWORD:?SMOKE_PASSWORD is required}"

ENV_FILE="${ENV_FILE:-.env.staging}"
PROJECT_NAME="${PROJECT_NAME:-slrms-staging}"
# Redis redelivers an unacknowledged task after the broker visibility timeout.
# The application default is 1,200 seconds, so leave a five-minute margin.
TIMEOUT="${PROCESSING_TIMEOUT_SECONDS:-1500}"
FIXTURE_LINES="${RECOVERY_FIXTURE_LINES:-5000}"
API_URL="${STAGING_API_URL%/}"
COMPOSE=(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.staging.yml)
WORK_DIR="$(mktemp -d)"
DOCUMENT_ID=""

refresh_access_token() {
  local http_status
  http_status="$(curl --silent --show-error -o "$WORK_DIR/refresh-response" -w '%{http_code}' -X POST -b "$WORK_DIR/cookies" -c "$WORK_DIR/cookies" "$API_URL/auth/refresh")"
  if [[ "$http_status" != "200" ]]; then
    echo "Unable to refresh the smoke access token (HTTP $http_status)." >&2
    return 1
  fi
  jq -er '.access_token' "$WORK_DIR/refresh-response" >"$WORK_DIR/token"
  echo "Access token refreshed while waiting for recovery." >&2
}

authenticated_request() {
  local method="$1"
  local output_file="$2"
  shift 2
  local http_status
  http_status="$(curl --silent --show-error -o "$output_file" -w '%{http_code}' -X "$method" -H "Authorization: Bearer $(<"$WORK_DIR/token")" "$@")"
  if [[ "$http_status" == "401" ]]; then
    refresh_access_token
    http_status="$(curl --silent --show-error -o "$output_file" -w '%{http_code}' -X "$method" -H "Authorization: Bearer $(<"$WORK_DIR/token")" "$@")"
  fi
  if (( http_status < 200 || http_status >= 300 )); then
    echo "Authenticated request failed: method=$method status=$http_status" >&2
    jq . "$output_file" >&2 2>/dev/null || cat "$output_file" >&2
    return 1
  fi
}

cleanup() {
  if [[ -n "$DOCUMENT_ID" && -s "$WORK_DIR/token" ]]; then
    authenticated_request DELETE "$WORK_DIR/cleanup-response" \
      "$API_URL/documents/$DOCUMENT_ID" >/dev/null || true
  fi
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

jq -n --arg email "$SMOKE_EMAIL" --arg password "$SMOKE_PASSWORD" \
  '{email:$email,password:$password}' >"$WORK_DIR/login.json"
curl --fail-with-body --silent --show-error \
  -c "$WORK_DIR/cookies" -H 'Content-Type: application/json' \
  --data-binary "@$WORK_DIR/login.json" \
  "$API_URL/auth/login" | jq -er '.access_token' >"$WORK_DIR/token"

MARKER="SLRMS-WORKER-RECOVERY-$(date -u +%Y%m%dT%H%M%SZ)"
for _ in $(seq 1 "$FIXTURE_LINES"); do
  printf '%s worker recovery payload\n' "$MARKER"
done >"$WORK_DIR/document.txt"

authenticated_request POST "$WORK_DIR/upload-response" \
  -F "file=@$WORK_DIR/document.txt;type=text/plain" -F "title=$MARKER" \
  "$API_URL/documents/upload"
DOCUMENT_ID="$(jq -er '.id' "$WORK_DIR/upload-response")"
echo "Created recovery document: $DOCUMENT_ID"

deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  authenticated_request GET "$WORK_DIR/metadata-response" "$API_URL/documents/$DOCUMENT_ID"
  metadata="$(<"$WORK_DIR/metadata-response")"
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

# Give recovery its own timeout budget; time spent waiting for PROCESSING must
# not reduce the Redis redelivery window.
deadline=$((SECONDS + TIMEOUT))
next_progress=$((SECONDS + 30))
while (( SECONDS < deadline )); do
  authenticated_request GET "$WORK_DIR/metadata-response" "$API_URL/documents/$DOCUMENT_ID"
  metadata="$(<"$WORK_DIR/metadata-response")"
  status="$(jq -r '.processing_status' <<<"$metadata")"
  if [[ "$status" == "done" ]]; then break; fi
  if [[ "$status" == "failed" ]]; then jq . <<<"$metadata"; exit 1; fi
  if (( SECONDS >= next_progress )); then
    remaining=$((deadline - SECONDS))
    attempts="$(jq -r '.processing_attempts' <<<"$metadata")"
    echo "Waiting for task redelivery: status=$status attempts=$attempts timeout_remaining=${remaining}s"
    next_progress=$((SECONDS + 30))
  fi
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
