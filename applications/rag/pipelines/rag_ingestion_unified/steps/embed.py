import os
from typing import Any, List

from applications.rag.pipelines.rag_ingestion.steps.configs import EmbedConfig
from applications.rag.pipelines.rag_ingestion.steps.models import ChunkedDocument, EmbeddedChunk, EmbedOutput
from libs.streampipe.observability import trace_action

@trace_action(step_name="embed")
async def embed_action(
    chunked_doc: ChunkedDocument, 
    infinity_client: Any, 
    config: EmbedConfig
) -> EmbedOutput:
    filename = os.path.basename(chunked_doc.source.source_path)
    
    # 1. Texte inklusive Preamble vorbereiten
    texts: List[str] = []
    for chunk in chunked_doc.chunks:
        preamble = chunk.meta.get("context_preamble", "")
        if preamble:
            texts.append(f"{preamble}\n\n{chunk.text}")
        else:
            texts.append(chunk.text)

    total_chunks = len(texts)
    print(f"🧬 [Embed] Starte Embedding für insgesamt {total_chunks} Chunks von {filename}...")

    # 2. Chunks in Batches unterteilen (Größe kommt aus config.batch_size)
    batch_size = config.batch_size
    dense_data = []

    for i in range(0, total_chunks, batch_size):
        batch_texts = texts[i:i + batch_size]
        print(f"   📥 Sende Batch {i // batch_size + 1} ({len(batch_texts)} Chunks) an Infinity...")
        
        try:
            # 🚀 DER FIX: Nutze die native, spezialisierte Methode des InfinityClient
            # Das umgeht call_async() und verhindert jeden 'unexpected keyword argument'-Fehler
            vectors = await infinity_client.embeddings_async(
                texts=batch_texts,
                model=config.model
            )
            
            # Da embeddings_async direkt eine Liste von Vektoren (Floats) liefert,
            # mappen wir sie in das von der Folgelogik erwartete Dict-Format
            for vec in vectors:
                dense_data.append({"embedding": vec})
                
        except Exception as e:
            print(f"❌ CRASH BEI BATCH-EMBEDDING in Datei {filename}!")
            print(f"Fehlertyp: {type(e).__name__} | Meldung: {str(e)}")
            raise

    # Validierung
    if len(dense_data) != total_chunks:
        raise ValueError(f"Fehler beim Embedding: Erwartete {total_chunks} Vektoren, erhielt {len(dense_data)}")

    # 3. Mappen der gesammelten Resultate auf die EmbeddedChunk-Struktur
    embedded_chunks: List[EmbeddedChunk] = []
    for i, chunk in enumerate(chunked_doc.chunks):
        dense_vec = dense_data[i]["embedding"]
        
        embedded_chunks.append(
            EmbeddedChunk(
                chunk=chunk,
                dense_vector=dense_vec,
                context_preamble=chunk.meta.get("context_preamble")
            )
        )

    return EmbedOutput(
        source_path=chunked_doc.source.source_path,
        embedded_chunks=embedded_chunks,
        parent_chunks=chunked_doc.parent_chunks,
        status="success"
    )




