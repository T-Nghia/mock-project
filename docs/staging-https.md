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
