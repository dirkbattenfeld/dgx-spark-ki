from pipelines.ingestion_engine.core.config import settings

print('DB URL:', settings.postgres_url) 
print('Concurrency:', settings.ingestion_worker_concurrency)