# SDK für S3 Storage
from libs.storage.client import StorageClient   
import logging
    
storage = StorageClient()
      
# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def delete_all_files_in_bucket(bucket_name: str = "bucket"):
    client = StorageClient()
    
    logger.info(f"Starte Löschvorgang für alle Dateien im S3-Bucket '{bucket_name}'.")

    successful_count = 0
    failed_files = []

    try:
        # Alle Dateien im Bucket ermitteln 
        # (Hinweis: Je nach genauer Implementierung des StorageClient kann die Methode 
        # z.B. auch client.list(), client.walk() oder client.glob() heißen)
        files_to_delete = client.list_files(bucket_name)
        total_files_count = len(files_to_delete)
        
        logger.info(f"Anzahl zu löschender Dateien: {total_files_count}")

        for filename_str in files_to_delete:
            try:
                # Datei löschen (Je nach Client auch client.delete() oder client.unlink())
                client.delete(bucket_name, filename_str)
                print ("DEBUG: ", filename_str, " gelöscht.")
                
                successful_count += 1
                logger.debug(f"Erfolgreich gelöscht: {filename_str}")
                
            except Exception as e:
                failed_files.append((filename_str, str(e)))
                logger.error(f"Fehler beim Löschen von '{filename_str}': {e}")

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Dateiliste aus Bucket '{bucket_name}': {e}")
        return

    failed_count = len(failed_files)

    # --- Zusammenfassung im Log ---
    logger.info("=== Löschvorgang abgeschlossen ===")
    logger.info(f"Gesamtanzahl Dateien: {total_files_count}")
    logger.info(f"Erfolgreich gelöscht: {successful_count}")
    logger.info(f"Nicht erfolgreich: {failed_count}")

    if failed_files:
        logger.warning("Folgende Dateien sind beim Löschen fehlgeschlagen:")
        for file_name, error_msg in failed_files:
            logger.warning(f" - {file_name} (Grund: {error_msg})")


if __name__ == "__main__":
    delete_all_files_in_bucket("miontec")