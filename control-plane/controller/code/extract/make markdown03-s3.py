import asyncio
import os
import time
from ki_dgxsdk.ki_sdk import DGX_Client
from libs.storage.client import StorageClient

# =====================================================================
# KONFIGURATION
# =====================================================================
CONFIG_PATH = "/app/code/microservices.yaml"
DISPATCHER_URL = "http://100.67.8.64:8000"

# S3 Zielkonfiguration
# Hinweis: Die S3-Zugangsdaten zieht sich der StorageClient automatisch aus der .env
S3_BUCKET = "docling-01"  # Dein Ziel-Bucket
S3_GLOB_PATTERN = "*.pdf"  # Sucht gezielt nach PDFs im gewünschten "Ordner"

# =====================================================================
# ASYNCHRONE VERARBEITUNGSSCHLEIFE
# =====================================================================
async def process_all_pdfs(use_dispatcher: bool, label: str):
    """
    Initialisiert das Storage- und KI-SDK, holt alle PDF-Pfade aus S3 
    und schiebt sie parallel an den Docling-Service.
    """
    print("\n" + "="*60)
    print(f"🚀 STARTE S3-TESTLAUF: {label}")
    print(f"   Dispatcher aktiv: {use_dispatcher}")
    print("="*60)

    # 1. Speicher-Client initialisieren (Zieht .env automatisch)
    print("🛰️ Verbinde mit S3-Speicher...")
    storage = StorageClient()

    # 2. KI-SDK-Client für diesen Testlauf instanziieren
    sdk = DGX_Client(
        config_path=CONFIG_PATH, 
        use_dispatcher=use_dispatcher,
        dispatcher_url=DISPATCHER_URL
    )
    docling = sdk.get_client("docling")

    # 3. Alle PDFs über das Storage-SDK einsammeln
    print(f"📂 Scanne S3 Bucket '{S3_BUCKET}' mit Pattern '{S3_GLOB_PATTERN}'...")
    try:
        # list_files liefert bereits vollqualifizierte s3://... Pfade zurück
        pdf_paths = storage.list_files(bucket=S3_BUCKET, glob_pattern=S3_GLOB_PATTERN)
    except Exception as e:
        print(f"❌ Fehler beim Abfragen der S3-Dateien: {e}")
        return
    
    if not pdf_paths:
        print(f"❌ Keine PDFs im Bucket '{S3_BUCKET}' mit dem Pattern '{S3_GLOB_PATTERN}' gefunden.")
        return

    pdf_paths = pdf_paths

    print(f"🎯 Gefundene S3-Dokumente ({len(pdf_paths)}):")
    for path in pdf_paths:
        print(f"  - {path}")
    print("-" * 60)

    # Hilfsfunktion für den einzelnen asynchronen Task
    async def send_single_request(s3_path):
        start_task = time.time()
        filename = os.path.basename(s3_path)
        
        print(f"🛫 Sende S3-Pfad an Docling: {s3_path}...")
        
        try:
            # Wir übergeben den vollen s3://-Pfad an 'source_pdf'
            result = await docling.call_async(
                endpoint_name="extract",
                source_pdf=s3_path,
                detailed_tables=True,
                ocr_enabled=True
            )
            
            duration = time.time() - start_task
            status = result.get("status", "error")
            print(f"🛬 Fertig: {filename} (Status: {status} | Zeit: {duration:.2f}s)")
            return result
        except Exception as e:
            print(f"💥 Fehler bei Task {filename}: {e}")
            return {"status": "error", "error": str(e)}

    # 4. Zeitmessung für den Gesamtlauf starten
    start_total = time.time()

    # Erstellt für jedes S3-PDF ein asynchrones Task-Objekt und feuert sie parallel ab
    tasks = [send_single_request(path) for path in pdf_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_duration = time.time() - start_total
    
    # 5. Auswertung des Testlaufs
    print("-" * 60)
    print(f"🏁 {label} BEENDET!")
    print(f"⏱️ Gesamtlaufzeit: {total_duration:.2f} Sekunden")
    
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "extracted")
    print(f"📊 Erfolgreich extrahiert: {success_count} von {len(pdf_paths)}")
    print("="*60 + "\n")


# =====================================================================
# MAIN ENTRYPOINT
# =====================================================================
async def main():
    # TESTLAUF 1: Direkt an FastAPI (Ohne Dispatcher-Queue)
    # Alle Requests treffen zeitgleich beim Uvicorn-Worker ein
    #await process_all_pdfs(
    #    use_dispatcher=False, 
    #    label="DIREKT AN FASTAPI VIA S3 (Volle Parallelität auf der GPU)"
    #)

    # Kurze Atempause für das System (Für zukünftige Verwendung bereitgestellt)
    # await asyncio.sleep(3)

    # TESTLAUF 2: Über den Dispatcher (Mit Queue-Steuerung)
    # Die Requests werden am Dispatcher gesammelt und gemäß Queue-Policy abgearbeitet
    await process_all_pdfs(
        use_dispatcher=True, 
        label="ÜBER DISPATCHER (Queue-gesteuert)"
    )

if __name__ == "__main__":
    # Startet die asynchrone Event-Loop von Python
    asyncio.run(main())