# --- STEP 1: EXTRACT LOGIK ---   
import os
from typing import Any
from applications.rag.pipelines.rag_ingestion.steps.configs import ExtractConfig
from applications.rag.pipelines.rag_ingestion.steps.models import ExtractInput, RawDocument
from libs.streampipe.observability import trace_action

@trace_action(step_name="extract")
async def extract_action(input_data: ExtractInput, docling_client: Any, config: ExtractConfig) -> RawDocument:
    filename = os.path.basename(input_data.source_path)
    print(f"🛫 [Extract] Sende S3-Pfad an Docling: {filename}...")
    
    base_dir = input_data.source_path.rsplit(".", 1)[0]
    docling_json_path = f"{base_dir}.docling.json"
        
    res = await docling_client.call_async(
        endpoint_name="extract",
        source_doc=input_data.source_path,
        detailed_tables=config.detailed_tables,
        ocr_enabled=config.ocr_enabled
    )
    
    return RawDocument(
        source_path=input_data.source_path,
        markdown_content=res.get("markdown_content", ""),
        json_path=docling_json_path,
        metadata=res.get("metadata", {}),
        status="success" if res else "error"
    )
    
