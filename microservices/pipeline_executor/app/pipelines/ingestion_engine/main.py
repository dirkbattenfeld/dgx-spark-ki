# pipeline_executor/app/pipelines/ingestion_engine/main.py

import logging
import sys
from datetime import timezone
from pathlib import Path

# Logging konfigurieren, damit wir sehen, was passiert
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("IngestionTestMain")

# Importiere deine Klassen (Pfade entsprechend deines Projekts anpassen)
from pipelines.ingestion_engine.core.models import PathRuleConfig, PipelineConfig
from pipelines.ingestion_engine.core.scanner import StorageSnapshotScanner


def run_scanner_test():
    logger.info("🚀 Starte Isolationstest für den Snapshot-Scanner...")

    # 1. Test-Konfiguration aufbauen (z. B. lokaler Ordner im Projekt oder ein Test-Pfad)
    # Passe den Pfad an ein echtes Verzeichnis auf deinem System an (z. B. ein lokales Testverzeichnis)
    test_target_dir = Path("/workspace/projects/rag02/data")
    test_target_dir.mkdir(exist_ok=True)

    pipeline_config = PipelineConfig(
        global_allowed_extensions=[".pdf", ".docx", ".xlsx"],
        watched_targets=[
            PathRuleConfig(
                path=test_target_dir,
                exclude_paths=[],
                exclude_extensions=[]
            )
        ]
    )

    # 2. StorageClient initialisieren (nutzt deine Umgebungsvariablen oder fällt auf file:// zurück)
    # Falls S3-Env-Vars fehlen, bricht der StorageClient evtl. beim Init ab. 
    # Für den reinen lokalen Test kannst du den StorageClient testweise mocken oder die .env prüfen.
    try:
        from storage.client import StorageClient
        storage_client = StorageClient()
    except Exception as e:
        logger.warning(f"⚠️ StorageClient konnte nicht mit S3-Env geladen werden ({e}). Verwende lokalen Fallback oder prüfe .env")
        raise

    # 3. Scanner instanzieren und ausführen
    scanner = StorageSnapshotScanner(config=pipeline_config, storage_client=storage_client)
    
    logger.info("🔍 Führe Scan aus...")
    snapshots = scanner.scan()

    # 4. Ergebnisse inspizieren
    logger.info(f"📊 Scan beendet. Gefundene Snapshots: {len(snapshots)}")
    for snap in snapshots:
        logger.info(f"   - Pfad: {snap.path} | Größe: {snap.size_bytes} Bytes | Mtime: {snap.mtime}")


if __name__ == "__main__":
    run_scanner_test()
