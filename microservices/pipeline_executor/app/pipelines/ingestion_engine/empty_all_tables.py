# pipelines/ingestion_engine/db/reset_db.py

import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from pipelines.ingestion_engine.db.session import async_session_maker, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("DBReset")

async def reset_database():
    logger.info("🗑️ Starte vollständigen Reset der Ingestion-Datenbank...")

    # Alle Tabellen des Ingestion-Modells 
    # CASCADE sorgt dafür, dass Foreign-Key-Abhängigkeiten (wie ingestion_jobs -> asset_registry) 
    # ohne Reihenfolgeprobleme mitgelöscht werden.
    # RESTART IDENTITY setzt Auto-Increment-Sequenzen wieder auf 1 zurück.
    tables_to_truncate = [
        "ingestion_jobs",
        "asset_registry"
    ]

    async with async_session_maker() as session:
        try:
            for table in tables_to_truncate:
                logger.info("   ↳ Leere Tabelle: %s", table)
                # TRUNCATE ... CASCADE ist in Postgres extrem schnell
                await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
            
            await session.commit()
            logger.info("✨ Datenbank erfolgreich geleert und zurückgesetzt.")

        except Exception as e:
            await session.rollback()
            logger.error("❌ Fehler beim Leeren der Datenbank: %s", e)
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_database())
