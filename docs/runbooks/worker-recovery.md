# Worker recovery drill

Run this drill on staging after a deployment that changes Celery, Redis, document
processing, or storage. It intentionally kills the staging worker; do not run it
against production.

## Prerequisites

- Run from the repository root on the staging host.
- `docker`, Docker Compose v2, `curl`, and `jq` are installed.
- `.env.staging` contains the active staging configuration.
- A dedicated active Teacher account is available.
- No release deployment is running at the same time.

## Run

```bash
export STAGING_API_URL=https://api.staging.example.com
export SMOKE_EMAIL=smoke@example.com
export SMOKE_PASSWORD='read-from-a-secret-manager'
bash scripts/drills/worker-recovery.sh
```

The script uploads a uniquely named text document, waits for `PROCESSING`, kills
and restarts the worker, waits for recovery, checks duplicate chunk indexes, and
deletes its document. A job that finishes before the worker is killed is reported
as inconclusive rather than a pass.

Record the date, commit SHA, elapsed recovery time, task attempts, and retained
logs in the incident/drill record. Investigate any document left in `PROCESSING`
after the configured timeout.
