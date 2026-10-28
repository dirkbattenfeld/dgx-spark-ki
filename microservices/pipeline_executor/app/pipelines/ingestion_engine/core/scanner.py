# pipeline_executor/app/pipelines/ingestion_engine/core/scanner.py

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from pipelines.ingestion_engine.core.models import (
    FileSnapshot,
    PathRuleConfig,
    PipelineConfig,
)

logger = logging.getLogger(__name__)


class StorageSnapshotScanner:
    def __init__(self, config: PipelineConfig, storage_client):
        self.config = config
        self.storage = storage_client

    def scan(self) -> List[FileSnapshot]:
        """
        Scannt alle konfigurierten Ziele (lokal oder S3) über den StorageClient,
        wendet Glob-Patterns und Filter an und liefert FileSnapshots zurück.
        """
        snapshots: List[FileSnapshot] = []

        for target in self.config.watched_targets:
            # target.path kann ein lokaler Pfad (z.B. "/data/docs") oder ein Bucket-Name sein
            bucket_or_path = str(target.path)
            
            # Baue ein Kombi-Glob aus den global erlaubten Endungen (z.B. "*.pdf,*.docx")
            # Oder nutze ein Standard-Muster wie "**/*"
            glob_pattern = "**/*" 

            logger.info("📂 Scanne Ziel '%s' mit Muster '%s'...", bucket_or_path, glob_pattern)

            try:
                # Nutze deinen StorageClient, um die Dateien aufzulösen
                file_urls = self.storage.list_files(bucket=bucket_or_path, glob_pattern=glob_pattern)
            except Exception as e:
                logger.error(f"❌ Fehler beim Auflösen des Pfades {bucket_or_path}: {e}")
                continue

            # Hole das zugrundeliegende fsspec-Filesystem, um an mtime und size zu kommen
            fs = self.storage._get_fs(self.storage._get_full_path(bucket_or_path))

            for file_url in file_urls:
                try:
                    # 1. Endungsprüfung gegen globale Regeln
                    if not self._is_allowed(file_url):
                        continue

                    # 2. Metadaten via fsspec abfragen (funktioniert für s3 und file gleichermaßen)
                    info = fs.info(file_url)
                    size_bytes = info.get("size", 0)
                    
                    # fsspec liefert mtime oft als Timestamp (float) oder datetime
                    raw_mtime = info.get("mtime") or info.get("updated")
                    if isinstance(raw_mtime, (int, float)):
                        mtime = datetime.fromtimestamp(raw_mtime, tz=timezone.utc)
                    elif isinstance(raw_mtime, datetime):
                        mtime = raw_mtime.astimezone(timezone.utc)
                    else:
                        mtime = datetime.now(timezone.utc)

                    # Pfad für das Pydantic-Modell aufbereiten
                    clean_path = Path(file_url.replace("file://", "").replace("s3://", ""))

                    snapshots.append(
                        FileSnapshot(
                            path=clean_path,
                            size_bytes=size_bytes,
                            mtime=mtime,
                            file_hash=None  # Wird im nächsten Schritt beim Diffing berechnet
                        )
                    )

                except Exception as e:
                    logger.warning(f"⚠️ Konnte Metadaten für Datei '{file_url}' nicht lesen: {e}")

        logger.info(f"✨ Snapshot-Scan abgeschlossen. {len(snapshots)} gültige Dateien im Speicher erfasst.")
        return snapshots

    def _is_allowed(self, file_url: str) -> bool:
        """Prüft die URL gegen die global erlaubten Dateiendungen."""
        ext = Path(file_url).suffix.lower()
        return ext in self.config.global_allowed_extensions
    