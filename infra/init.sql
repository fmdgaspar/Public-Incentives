-- Initialize PostgreSQL database for AI Challenge
-- This script is run when the database container starts for the first time

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized with pgvector extension';
END
$$;

