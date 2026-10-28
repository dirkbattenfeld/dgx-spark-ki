# pipeline_executor/app/pipelines/ingestion_engine/db/session.py

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pipelines.ingestion_engine.core.config import settings

# 1. Die asynchrone Engine (Das Kraftwerk / Verbindungspool)
engine = create_async_engine(
    settings.postgres_url,
    echo=False,  # Setze auf True, wenn du alle SQL-Queries im Log sehen willst (super zum Debuggen)
    future=True,
)

# 2. Die Async Session Factory (Die Fabrik für transaktionssichere Sessions)
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Wichtig bei Async: Objekte bleiben nach dem Commit lesbar, ohne dass ein neuer DB-Query nötig ist
    autoflush=False,
)