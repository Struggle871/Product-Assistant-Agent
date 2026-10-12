CREATE EXTENSION IF NOT EXISTS vector;

-- pg_search is provided by the ParadeDB image. Keep startup explicit so an
-- incompatible image fails during readiness instead of during ingestion.
CREATE EXTENSION IF NOT EXISTS pg_search;
