import asyncio
import os
import time
from pathlib import Path
from ki_dgxsdk.ki_sdk import DGX_Client

# =====================================================================
# KONFIGURATION
# =====================================================================
CONFIG_PATH = "/app/code/microservices.yaml"
HOST_PDF_DIR = "/app/projects/extract/data/paper/fairness"
GX10_PDF_DIR = "/projects/rag/data/paper/fairness"
DISPATCHER_URL = "http://gx10:8000"

# =====================================================================
# ASYNCHRONE VERARBEITUNGSSCHLEIFE
# =====================================================================
async def process_all_pdfs(use_dispatcher: bool, label: str):
    """
    Initialisiert das SDK und schickt alle PDFs aus dem Verzeichnis 
    asynchron und parallel an den Docling-Service.
    """
    print("\n" + "="*60)
    print(f"🚀 STARTE TESTLAUF: {label}")
    print(f"   Dispatcher aktiv: {use_dispatcher}")
    print("="*60)

    # 1. SDK-Client für diesen Testlauf instanziieren
    sdk = DGX_Client(
        config_path=CONFIG_PATH, 
        use_dispatcher=use_dispatcher,
        dispatcher_url=DISPATCHER_URL
    )
    docling = sdk.get_client("docling")

    # 2. Alle PDFs im Verzeichnis einsammeln
    pdf_paths = [
        str(p) for p in Path(HOST_PDF_DIR).glob("*.pdf") 
        if p.is_file()
    ]
    
    if not pdf_paths:
        print(f"❌ Keine PDFs im Verzeichnis {HOST_PDF_DIR} gefunden.")
        return

    print(f"📂 Gefundene Dokumente ({len(pdf_paths)}):")
    for path in pdf_paths:
        print(f"  - {os.path.basename(path)}")
    print("-" * 60)

    # Hilfsfunktion für den einzelnen asynchronen Task
    async def send_single_request(pdf_path):
        start_task = time.time()
        filename = os.path.basename(pdf_path)
        gx10_pdf_path = os.path.join(GX10_PDF_DIR, filename)
        
        print(f"🛫 Sende: {gx10_pdf_path}...")
        
        # Aufruf über die native asynchrone Schnittstelle des MappingClients
        result = await docling.call_async(
            endpoint_name="extract",
            source_pdf=gx10_pdf_path,
            detailed_tables=True,
            ocr_enabled=True
        )
        
        duration = time.time() - start_task
        status = result.get("status", "error")
        print(f"🛬 Fertig: {filename} (Status: {status} | Zeit: {duration:.2f}s)")
        return result

    # 3. Zeitmessung für den Gesamtlauf starten
    start_total = time.time()

    # Erstellt für jedes PDF ein asynchrones Task-Objekt und feuert sie parallel ab
    tasks = [send_single_request(path) for path in pdf_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_duration = time.time() - start_total
    
    # 4. Auswertung des Testlaufs
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
    #TESTLAUF 1: Direkt an FastAPI (Ohne Dispatcher-Queue)
    #Alle Requests treffen zeitgleich beim Uvicorn-Worker ein
    await process_all_pdfs(
        use_dispatcher=False, 
        label="DIREKT AN FASTAPI (Volle Parallelität auf der GPU)"
    )

    # Kurze Atempause für das System
    #await asyncio.sleep(3)

    # TESTLAUF 2: Über den Dispatcher (Mit Queue-Steuerung)
    # Die Requests werden am Dispatcher gesammelt und gemäß Queue-Policy abgearbeitet
    #await process_all_pdfs(
    #    use_dispatcher=True, 
    #    label="ÜBER DISPATCHER (Queue-gesteuert)"
    #)

if __name__ == "__main__":
    # Startet die asynchrone Event-Loop von Python
    asyncio.run(main())
