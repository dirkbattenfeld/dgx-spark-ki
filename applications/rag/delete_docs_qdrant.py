from typing import List

# Auf DGXClient umstellen
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

async def purge_documents_from_qdrant(
    qdrant_client: AsyncQdrantClient, 
    source_paths: List[str], 
    child_collection_name: str
) -> None:
    """
    Löscht alle Child- und Parent-Chunks für eine Liste von source_paths
    rückstandslos aus beiden Qdrant-Kollektionen via Payload-Filter.
    """
    if not source_paths:
        print("⚠️ [Purge] Keine source_paths übergeben. Breche ab.")
        return

    # 1. Bestimme den Namen der Parent-Kollektion (Passe das Suffix an dein System an)
    parent_collection_name = f"{child_collection_name}_parents"
    
    print(f"🧹 [Purge] Starte Bereinigung für {len(source_paths)} Dokument(e)...")
    print(f"📦 Ziel-Kollektionen: Chunks -> '{child_collection_name}' | Parents -> '{parent_collection_name}'")

    # 2. Bauen des Filters: Wir löschen alle Punkte, deren 'source_path' in unserer Liste liegt
    purge_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="meta.source_path",  # Nutze "source_path", falls es flach im Payload liegt
                match=models.MatchAny(any=source_paths)
            )
        ]
    )

    try:
        # 3. Löschbefehl an die Child-Kollektion senden
        child_res = await qdrant_client.delete(
            collection_name=child_collection_name,
            points_selector=models.FilterSelector(filter=purge_filter)
        )
        print(f"✅ [Purge] Childs gelöscht aus '{child_collection_name}' (Status: {child_res.status})")

        # 4. Löschbefehl an die Parent-Kollektion senden
        parent_res = await qdrant_client.delete(
            collection_name=parent_collection_name,
            points_selector=models.FilterSelector(filter=purge_filter)
        )
        print(f"✅ [Purge] Parents gelöscht aus '{parent_collection_name}' (Status: {parent_res.status})")
        
        print("🎉 [Purge] Bereigung erfolgreich abgeschlossen.")

    except Exception as e:
        print(f"❌ [Purge] Kritischer Fehler beim Löschen in Qdrant: {e}")
        raise


# --- BEISPIEL FÜR DEN AUFRUF IN DEINER PIPELINE ---
# async def main():
#     # Falls dein DGXClient den echten AsyncQdrantClient kapselt:
#     client = AsyncQdrantClient(url="http://localhost:6333")
#     
#     zu_loeschende_dateien = [
#         "N:/Verträge/2026/Mustervertrag_alt.pdf",
#         "N:/Dokumente/Does fairness prevent market clearing.pdf"
#     ]
#     
#     await purge_documents_from_qdrant(
#         qdrant_client=client,
#         source_paths=zu_loeschende_dateien,
#         child_collection_name="knowledge_chunks"
#     )