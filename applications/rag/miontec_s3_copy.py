# SDK für S3 Storage
from libs.storage.client import StorageClient   
import logging
from pathlib import Path
import shutil
    
storage = StorageClient()
      
# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def upload_local_dir_to_s3(local_dir: str = "local_dir", bucket_name: str = "bucket"):
    client = StorageClient()
    local_path = Path(local_dir)
    
    if not local_path.exists() or not local_path.is_dir():
        logger.error(f"Das lokale Verzeichnis '{local_dir}' existiert nicht oder ist kein Verzeichnis.")
        return

    # Alle Dateien rekursiv ermitteln
    files_to_copy = [p for p in local_path.rglob("*") if p.is_file()]
    total_files = len(files_to_complex := files_to_copy) # Gesamtzahl ermitteln
    total_files_count = len(files_to_files := files_to_copy)
    
    logger.info(f"Starte Kopiervorgang von '{local_dir}' nach S3-Bucket '{bucket_name}'.")
    logger.info(f"Anzahl zu kopierender Dateien: {total_files_count}")

    successful_count = 0
    failed_files = []

    abs_local_dir = str(local_path.resolve())

    for file_path in files_to_files:
        rel_path = file_path.relative_to(local_path)
        # S3-kompatible Slashes erzwingen (auch unter Windows)
        filename_str = str(rel_path).replace("\\", "/")
        
        try:
            # Lokale Datei im Binärmodus öffnen und in den S3-Bucket streamen
            with client.open(abs_local_dir, filename_str, mode="rb") as src_file:
                with client.open(bucket_name, filename_str, mode="wb") as dest_file:
                    shutil.copyfileobj(src_file, dest_file)
            
            successful_count += 1
            logger.debug(f"Erfolgreich kopiert: {filename_str}")
            
        except Exception as e:
            failed_files.append((filename_str, str(e)))
            logger.error(f"Fehler beim Kopieren von '{filename_str}': {e}")

    failed_count = len(failed_files)

    # --- Zusammenfassung im Log ---
    logger.info("=== Kopiervorgang abgeschlossen ===")
    logger.info(f"Gesamtanzahl Dateien: {total_files_count}")
    logger.info(f"Erfolgreich kopiert: {successful_count}")
    logger.info(f"Nicht erfolgreich: {failed_count}")

    if failed_files:
        logger.warning("Folgende Dateien sind beim Kopieren fehlgeschlagen:")
        for file_name, error_msg in failed_files:
            logger.warning(f" - {file_name} (Grund: {error_msg})")


if __name__ == "__main__":
    upload_local_dir_to_s3("projects/miontec/docs", "miontec")
