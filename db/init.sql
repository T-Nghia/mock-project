-- Runs automatically on first Postgres container start (mounted into
-- /docker-entrypoint-initdb.d). Enables pgvector used by document_chunks.embedding.
CREATE EXTENSION IF NOT EXISTS vector;
