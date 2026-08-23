# applications/rag_gui/core/retrieve_qdrant.py
from typing import List
from rag_gui.core.models import RetrievalChunk


async def retrieve_chunks_by_source_path(
    qdrant_client,
    collection_name: str,
    source_path: str
) -> List[RetrievalChunk]:
    """
    Retrieves all chunks from a Qdrant collection where the metadata field `source_path`
    exactly matches the given `source_path`.

    Args:
        qdrant_client: The Qdrant client instance (must support async `scroll`).
        collection_name: Name of the Qdrant collection to query.
        source_path: Exact value to match in the `meta.source_path` metadata field.

    Returns:
        List[RetrievalChunk]: List of matching chunks, parsed into RetrievalChunk objects.
    """
    print(f"[DEBUG retrieve_qdrant] START: collection_name={collection_name}, source_path={source_path}")

    from qdrant_client.http import models as qdrant_models

    # Build filter: match on metadata.source_path
    filter_ = qdrant_models.Filter(
        must=[
            qdrant_models.FieldCondition(
                key="meta.source_path",
                match=qdrant_models.MatchValue(value=source_path)
            )
        ]
    )

    print(f"[DEBUG retrieve_qdrant] filter built, calling scroll...")
    # Perform the scroll (no vector needed, just filter)
    scroll_result = await qdrant_client.client.scroll(
        collection_name=collection_name,
        scroll_filter=filter_,
        with_payload=True,
        with_vectors=False,
        limit=1000
    )
    print(f"[DEBUG retrieve_qdrant] scroll returned, result type={type(scroll_result)}")

    points, _ = scroll_result
    print(f"[DEBUG retrieve_qdrant] scroll_result points count={len(points)}")
    chunks: List[RetrievalChunk] = []

    for idx, point in enumerate(points):
        payload = point.payload or {}
        # Parse parent chunk from ba25-paper_parents
        parent_collection = "ba25-paper_parents"
        parent_id = payload.get("parent_id")
        parent_text = ""
        if parent_id:
            try:
                parent_point = await qdrant_client.client.scroll(
                    collection_name=parent_collection,
                    scroll_filter=qdrant_models.Filter(
                        must=[qdrant_models.FieldCondition(
                            key="id",
                            match=qdrant_models.MatchValue(value=parent_id)
                        )]
                    ),
                    with_payload=True,
                    with_vectors=False,
                    limit=1
                )
                parent_points, _ = parent_point
                if parent_points:
                    parent_text = parent_points[0].payload.get("text", "")
            except Exception as e:
                print(f"[DEBUG retrieve_qdrant] WARNING: Failed to fetch parent {parent_id}: {e}")
        
        # Use the existing factory method to parse the payload into RetrievalChunk
        chunk = RetrievalChunk.from_enriched_hit(
            hit_dict={
                "parent_id": parent_id,
                "parent_text": parent_text,
                "context_preamble": payload.get("context_preamble"),
                "rerank_hit": {
                    "original_hit": {
                        "id": payload.get("id"),
                        "text": payload.get("text"),
                        "score": payload.get("score", 0.0),
                        "rank": payload.get("rank", idx + 1),
                        "meta": {
                            "source_path": payload.get("source_path"),
                            "headings": payload.get("headings", [])
                        }
                    }
                }
            },
            fallback_index=idx
        )
        chunks.append(chunk)

    print(f"[DEBUG retrieve_qdrant] END: returning {len(chunks)} chunks")
    return chunks
