import os
from ki_dgxsdk.ki_sdk import DGX_Client

# =====================================================================
# KONFIGURATION
# =====================================================================
CONFIG_PATH = "/app/code/microservices.yaml"
use_dispatcher = False
DISPATCHER_URL = "http://100.67.8.64:8000"

source_pdf = "s3://docling-01/Does fairness prevent market clearing.pdf"

# S3 Zielkonfiguration
# Hinweis: Die S3-Zugangsdaten zieht sich der StorageClient automatisch aus der .env
S3_BUCKET = "docling-01"  # Dein Ziel-Bucket

sdk = DGX_Client(
        config_path=CONFIG_PATH, 
        use_dispatcher=use_dispatcher,
        dispatcher_url=DISPATCHER_URL
    )
  
docling = sdk.get_client("docling")

base_dir, _ = os.path.splitext(source_pdf)
docling_json_path = f"{base_dir}.docling.json"

payload = {
    "json_path": docling_json_path,
    "source_path": source_pdf,
    "config": {
        "tokenizer_name": "BAAI/bge-m3",
        "child_max_tokens": 1024,
        "max_child_chunks_per_parent": 150,  
        "parent_overlap_chunks": 0,          
        "merge_peers": True
    }
}

print("\nSende Request an den /chunk Endpunkt...")

try:
    result = docling.call(
        endpoint_name="chunk",
        json_path=docling_json_path,
        source_path=source_pdf,
        config = {
            "tokenizer_name": "BAAI/bge-m3",
            "child_max_tokens": 1024,
            "max_child_chunks_per_parent": 150,  
            "parent_overlap_chunks": 0,          
            "merge_peers": True
        }
    )

    print("\n--- CHUNKING ERFOLGREICH ABGESCHLOSSEN ---")
    metadata = result.get("metadata", {})
    parents = result.get("parents", [])
    children = result.get("children", [])
    
    print(f"Generierte Parent-Objekte (Kollektion 1):  {metadata.get('total_parents', len(parents))}")
    print(f"Generierte Child-Objekte  (Kollektion 2):  {metadata.get('total_children', len(children))}")
    print(f"Verwendeter Tokenizer:                     {metadata.get('tokenizer')}")
    print(f"Max. Childs pro Parent (Limit):            {payload['config']['max_child_chunks_per_parent']}")
    print(f"Eingestellter Parent-Overlap:             {payload['config']['parent_overlap_chunks']}")
    
    chunks_file_path = f"{base_dir}.docling.chunks.json"
    print(f"\n[INFO] Normalisierte Daten erfolgreich persistiert unter:\n--> {chunks_file_path}")

except Exception as e:
    print(f"\n[FEHLER] Der API-Aufruf ist fehlgeschlagen: {e}")
    
    

