# microservices/rag/src/main.py
from microservices.shared_runtime.app_factory import create_generic_service
from applications.rag.pipelines.rag_request.api_bridge import (
    build_rag_topology, transform_pool_to_api_response
)

# Wir bauen die App, indem wir die RAG-Logik injizieren
app = create_generic_service(
    title="DGX Spark Stack - RAG Service Runtime",
    topology_factory=build_rag_topology,
    transform_factory=transform_pool_to_api_response
)

