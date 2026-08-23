# applications executable in control planes
## Control Plane "controller"
* rag: RAG Sytem with ingestion pipeline, request pipeline
* rag: pipelines depend on runner: streampipe, clients: storage, ki_dgxsdk
* rag: depends on microservices: garage-s3, qdrant, optional: filestash, dispatcher
* rag: depends on ki-services: docling, infinity, vllm

## Controll Plane "dagster"
* not tested (todo)


