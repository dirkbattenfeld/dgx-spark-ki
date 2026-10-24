import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Füge /app zum Python-Pfad hinzu (4 Ebenen nach oben vom aktuellen Skript aus)
# Path(__file__).resolve() -> env.py
# .parents[3] -> /app
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Importiere Pydantic-Settings und SQLAlchemy Base
from pipelines.ingestion_engine.core.config import settings
from pipelines.ingestion_engine.db.models import Base

config = context.config

# Dynamische Überschreibung der URL aus den Pydantic-Settings
config.set_main_option("sqlalchemy.url", settings.postgres_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    # Hier erstellen wir explizit die asynchrone Engine mit deiner postgres_url
    connectable = create_async_engine(settings.postgres_url)

    async with connectable.connect() as connection:
        # Führt die synchronen Alembic-Migrationen im asynchronen Kontext aus
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
