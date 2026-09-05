# Staging HTTPS

Staging uses the production Compose overlay plus a small Caddy overlay. Caddy is
the only public service, redirects HTTP to HTTPS, and obtains/renews public TLS
certificates automatically. Application, API, PostgreSQL, Redis, and MinIO stay
on the private Compose network.

## Prerequisites

- A server with Docker Engine and Docker Compose v2.
- TCP ports 80 and 443 and UDP port 443 open to the internet.
- `A`/`AAAA` records for the application and API domains pointing to the server.
  Remove an `AAAA` record if the server is not reachable over IPv6.

## Configure

Copy `.env.staging.example` to `.env.staging`. Replace every sample credential,
and keep staging credentials, database, bucket, and domains separate from
production. `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL` must match those domains.

Do not commit `.env.staging`. Validate the fully merged configuration before the
first deployment:

```bash
docker compose -p slrms-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.staging.yml config --quiet
```

## Deploy

```bash
docker compose -p slrms-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.staging.yml up -d --build
```

The one-shot `migrate` service applies migrations and seed data before the API
and worker start. On first launch, certificate issuance can take a short time.

Verify the deployment:

```bash
curl -fsS https://api.staging.example.com/health/ready
curl -I https://staging.example.com
docker compose -p slrms-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.staging.yml ps
```

Replace the example hostnames in the `curl` commands. If TLS issuance fails,
inspect `caddy` logs and confirm DNS and inbound ports 80/443. Back up the
staging database, object storage, and the `caddy_data` volume according to the
same policy used for production.

## Post-deployment smoke test

The `Post-deploy smoke test` GitHub Actions workflow runs automatically after a
successful GitHub Deployment, and can also be started manually. Configure these
GitHub Environment values for `staging`:

- Variables: `STAGING_APP_URL` and `STAGING_API_URL`.
- Secrets: `SMOKE_EMAIL` and `SMOKE_PASSWORD`.

The smoke user must already exist, be active, have the full name `Smoke Test`,
and use the `teacher` role because the dashboard endpoint is not available to
students. Keep it dedicated to monitoring and do not grant it administrative
access. A run verifies dependency readiness, loads the deployed
login page, signs in through the browser, fetches the current user, and renders
the dashboard. Failed runs retain screenshots, video, trace, and an HTML report
for seven days.

Run the same suite locally against any deployed environment:

```bash
cd e2e
npm install
npx playwright install chromium
APP_URL=https://staging.example.com \
API_URL=https://api.staging.example.com \
SMOKE_EMAIL=smoke@example.com SMOKE_PASSWORD='replace-me' npm test
```

Use `npm run test:smoke` for the short deployment gate. The slower document
lifecycle suite runs nightly or manually through the `Staging document lifecycle
E2E` workflow and can be invoked locally with `npm run test:lifecycle`.

## Recovery drills

After staging is healthy, run the operational drills documented here:

- [Worker recovery drill](runbooks/worker-recovery.md)
- [Backup and restore drill](runbooks/backup-restore.md)

These drills intentionally restart the worker or create isolated restore targets;
run them from the staging host outside an active deployment window.
