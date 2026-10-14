-- Wird beim ersten Start automatisch ausgeführt
CREATE USER ingestion_user WITH PASSWORD 'ingestion_pw';
CREATE DATABASE ingestion_db OWNER ingestion_user;
GRANT ALL PRIVILEGES ON DATABASE ingestion_db TO ingestion_user;

-- Falls du später noch eine für den Orchestrator brauchst:
-- CREATE USER orchestrator_user WITH PASSWORD '...';
-- CREATE DATABASE orchestrator_db OWNER orchestrator_user;
-- GRANT ALL PRIVILEGES ON DATABASE orchestrator_db TO orchestrator_user;
