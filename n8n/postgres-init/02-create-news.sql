-- Create the 'news' database used by the tech-news aggregator.
-- The n8n database is already created by the official Postgres image
-- via POSTGRES_DB. This file runs after that on first boot.
SELECT 'CREATE DATABASE news'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'news')\gexec
