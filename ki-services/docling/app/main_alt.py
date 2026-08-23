import os
import io
import sys
import json
import logging
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Docling Core & Base Imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument
from docling.chunking import HybridChunker
from transformers import AutoTokenizer

# SOTA Tabellen- & Pipeline-Optionen
from docling.datamodel.base_models import InputFormat  # Definiert die erlaubten Dateitypen
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode  # Steuert die KI-Modell-Backends
from docling.models.stages.ocr.tesseract_ocr_model import TesseractOcrOptions

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docling-service")

# SDK für S3 Storage
from storage.client import StorageClient

# --- Daten-Modelle (API-Schnittstellen) ---

class ExtractRequest(BaseModel):
    source_pdf: str
    start_page: Optional[int] = Field(None, description="Erste zu ladende Seite (1-basiert)")
    end_page: Optional[int] = Field(None, description="Letzte zu ladende Seite (inklusive)")
    detailed_tables: bool = Field(True, description="True = ACCURATE Mode (TableFormer), False = FAST Mode")
    ocr_enabled: bool = Field(True, description="Schaltet die Tesseract-Texterkennung ein/aus")

class ChunkConfig(BaseModel):
    tokenizer_name: str = "BAAI/bge-m3"
    child_max_tokens: int = Field(1024, description="Großzügiges Limit für semantische Child-Einheiten")
    max_child_chunks_per_parent: int = Field(6, description="Das absolute Maximum an Childs pro Parent")
    parent_overlap_chunks: int = Field(1, description="Wie viele Child-Chunks sich zwischen zwei Parents überlappen sollen")
    merge_peers: bool = True

class ChunkRequest(BaseModel):
    json_path: str = Field(..., description="Pfad zur generierten *.docling.json Datei url: s3 oder pfad")
    source_path: str = Field(..., description="Originalpfad der Quell-PDF (für das Source-Metadatum)")
    config: ChunkConfig = Field(default_factory=ChunkConfig)
    
# --- Globaler State & Lifespan ---
class GlobalState:
    """Hält die teuren Modelle im Speicher."""
    storage: Optional[StorageClient] = None
    converter: Optional[DocumentConverter] = None
    default_chunker: Optional[HybridChunker] = None
    active_tokenizer_name: Optional[str] = None

state = GlobalState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisiere StorageClient und Modelle beim Start des Containers."""
    logger.info("Starte Docling-Microservice und initialisiere Subsysteme...")
    
    try:
        # 1. SDK-Client instanziieren 
        state.storage = StorageClient()
    
        logger.info("Starte Initialisierung der Modelle auf der GPU...")
        
        # Cuda Check
        cuda_available = torch.cuda.is_available()
        
        if not cuda_available:
            logger.critical("FATAL: CUDA ist nicht verfügbar! Der Service wird gestoppt.")
            sys.exit(1)  # Stoppt den Container kontrolliert mit Fehlerstatus
        
        logger.info(f"Aktive GPU erkannt: {torch.cuda.get_device_name(0)}")
        
        # Pipeline-Optionen für pdf konfigurieren
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_table_structure = True  #erweiterte Tabellenanalyse
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.ocr_options = TesseractOcrOptions(
            lang=["deu", "eng"]  
        )
                  
        # Converter mit Pipeline-Optionen laden
        state.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend_constraints={"device": "cuda"}  
                )
            }
        )
        logger.info("Docling-Pipeline erfolgreich geladen: TableFormer (Accurate) läuft auf CUDA.")
        
        # Standard-Chunker vorab laden (BGE-M3)
        default_tokenizer = "BAAI/bge-m3"
        tokenizer = AutoTokenizer.from_pretrained(default_tokenizer)
        state.default_chunker = HybridChunker(
            tokenizer=tokenizer,
            max_tokens=512,
            merge_peers=True
        )
        state.active_tokenizer_name = default_tokenizer

        logger.info(f"Modelle geladen. Standard-Tokenizer: {default_tokenizer}")
    except Exception as e:
        logger.critical(f"FATAL: Fehler bei der Initialisierung des Lifespans: {e}", exc_info=True)
        sys.exit(1)
    yield
    # Aufräumen beim Herunterfahren
    logger.info("Fahre Service herunter...")

app = FastAPI(title="Docling Microservice (Optimized)", lifespan=lifespan)

# --- API Endpunkte ---
@app.post("/extract")
async def extract_document(request: ExtractRequest):
    """
    Konvertiert PDF -> JSON (Struktur) und Markdown.
    Verarbeitet s3:// oder lokale Pfade vollkommen generisch.
    Nutzt den über lifespan bereitgestellten StorageClient.
    """
    # Client aus dem App-State ziehen
    storage = state.storage
    
    try:
        # Existenzprüfung über SDK
        if not storage.exists(request.source_pdf):
            raise HTTPException(
                status_code=404, 
                detail=f"Datei nicht gefunden: {request.source_pdf}"
            )
                    
        # Aktuelle PipelineOptions für den Request bauen. 
        req_options = PdfPipelineOptions()
        
        # Tabellen-Modus dynamisch anpassen
        req_options.do_table_structure = True
        if request.detailed_tables:
            req_options.table_structure_options.mode = TableFormerMode.ACCURATE
        else:
            req_options.table_structure_options.mode = TableFormerMode.FAST

        # OCR flexibel steuern
        if request.ocr_enabled:
            req_options.ocr_options = TesseractOcrOptions(lang=["deu", "eng"])
        else:
            req_options.ocr_options.enabled = False
            logger.info("OCR für diesen Request deaktiviert (Nativ-Text-Modus).")
            
        state.converter.format_to_options[InputFormat.PDF] = PdfFormatOption(
            pipeline_options=req_options,
            backend_constraints={"device": "cuda"}
        )
        
        convert_kwargs = {}
            
        # Streamen über SDK
        with storage.open(request.source_pdf, mode="rb") as file_stream:
            file_bytes = io.BytesIO(file_stream.read())
            
        file_name = Path(request.source_pdf).name
        docling_stream = DocumentStream(name=file_name, stream=file_bytes)
            
        convert_kwargs["source"] = docling_stream
        
        if request.start_page is not None and request.end_page is not None:
            if request.start_page < 1 or request.end_page < request.start_page:
                raise HTTPException(status_code=400, detail="Ungültige Seitenspezifikation.")
            # Explizites Tupel für Pydantic bereitstellen
            convert_kwargs["page_range"] = (request.start_page, request.end_page)
            logger.info(f"Native Seiteneinschränkung aktiv: Seiten {request.start_page} bis {request.end_page}")
            
        elif request.start_page is not None:
            # Einzelne Seite als Start- und Endpunkt im Tupel definieren
            convert_kwargs["page_range"] = (request.start_page, request.start_page)
            logger.info(f"Native Seiteneinschränkung aktiv: Nur Seite {request.start_page}")
                        
        # Converter mit den aktuellen Optionen aufrufen
        result = state.converter.convert(**convert_kwargs)
                       
        doc_dict = result.document.export_to_dict()  # Das native Docling-JSON für den Chunker
        
        hybrid_markdown_lines = []
        extracted_tables_json = {}
        table_counter = 0

        # Wir durchlaufen das Dokument chronologisch Element für Element
        for element, level in result.document.iterate_items():
            
            # Erkennung von Tabellen-Elementen
            if element.label == "table" or hasattr(element, "export_to_dataframe"):
                table_counter += 1
                table_id = f"table_{table_counter:03d}"
                
                try:
                    # Wandelt die Tabellenstruktur via Pandas in ein flaches JSON-Objekt-Array um
                    df = element.export_to_dataframe()
                    table_dict = df.to_dict(orient="records")
                except Exception as table_err:
                    logger.warning(f"Fehler beim Tabellenexport ({table_id}): {table_err}")
                    table_dict = {"error": f"Konnte Tabellenstruktur nicht extrahieren: {str(table_err)}"}
                
                # Seitennummer der Tabelle ermitteln (falls vorhanden)
                page_no = element.prov[0].page_no if (hasattr(element, "prov") and element.prov) else None
                
                # Eintrag für das separate Tabellen-JSON vorbereiten
                extracted_tables_json[table_id] = {
                    "page_index": page_no,
                    "data": table_dict
                }
                
                # 2. Tabellen-JSON als Inline-Block in das hybride Markdown einbetten
                hybrid_markdown_lines.append(f"<!-- START_{table_id} -->")
                hybrid_markdown_lines.append(json.dumps(table_dict, ensure_ascii=False))
                hybrid_markdown_lines.append(f"<!-- END_{table_id} -->")
                
            else:
                # Text- und Strukturelemente verarbeiten
                if hasattr(element, "text") and element.text:
                    if element.label == "heading":
                        # Rekonstruktion der korrekten Markdown-Überschriften-Ebene
                        prefix = "#" * min(level + 1, 6)
                        hybrid_markdown_lines.append(f"{prefix} {element.text}")
                    else:
                        # Normaler Fließtext / Absätze
                        hybrid_markdown_lines.append(element.text)

        # Generierung des finalen hybriden Markdown-Strings
        hybrid_markdown_content = "\n\n".join(hybrid_markdown_lines)
        
        # Pfade ableiten
        base_path, _ = os.path.splitext(request.source_pdf)
        json_output_path = f"{base_path}.docling.json"
        md_output_path = f"{base_path}.md"
        tables_output_path = f"{base_path}.tables.json"  
        log_output_path = f"{base_path}.extract.log.json" 
        
        # Metadaten-Payload für das Log
        meta_processed = {
            "pages": convert_kwargs.get("page_range", "All"),
            "table_mode": "ACCURATE" if request.detailed_tables else "FAST",
            "ocr_active": request.ocr_enabled,
            "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            "extracted_tables_count": table_counter
        }

        # Ergebnisse über die .open()-Methode des SDKs wegschreiben
        with storage.open(json_output_path, mode="w") as f:
            json.dump(doc_dict, f, ensure_ascii=False)

        with storage.open(md_output_path, mode="w") as f:
            f.write(hybrid_markdown_content)

        with storage.open(tables_output_path, mode="w") as f:
            json.dump(extracted_tables_json, f, ensure_ascii=False, indent=2)

        with storage.open(log_output_path, mode="w") as f:
            json.dump(meta_processed, f, ensure_ascii=False, indent=2)

        # Response-Objekt 
        response_data = {
            "json_path": json_output_path,
            "markdown_path": md_output_path,
            "tables_path": tables_output_path,  
            "log_path": log_output_path,
            "status": "extracted",
            "meta_processed": meta_processed,
            "markdown": hybrid_markdown_content  
        }

        return response_data        
        

    except Exception as e:
        logger.error(f"Extraktionsfehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chunk")
async def chunk_document_normalized(request: ChunkRequest):
    """
    Erzeugt strikt getrennte Parent- und Child-Strukturen für ein
    normalisiertes Zwei-Kollektionen-Modell in Qdrant. Ohne Textduplizierung.
    """
    
    # Client aus dem App-State ziehen
    storage = state.storage
    
    try:
        if not storage.exists(request.json_path):  # <-- GEÄNDERT
            raise HTTPException(status_code=404, detail="Docling-JSON nicht gefunden.")
        
        with storage.open(request.json_path, mode="r") as f:
            doc_data = json.load(f)
            
        doc = DoclingDocument.model_validate(doc_data)

        tokenizer = AutoTokenizer.from_pretrained(request.config.tokenizer_name)
        max_model_length = getattr(tokenizer, "model_max_length", 8192)
        if max_model_length > 8192:
            max_model_length = 8192

        active_chunker = HybridChunker(
            tokenizer=tokenizer,
            max_tokens=request.config.child_max_tokens,
            merge_peers=request.config.merge_peers
        )

        # 1. Schritt: Child-Basis-Chunks extrahieren
        base_chunks = list(active_chunker.chunk(dl_doc=doc))
        
        prepared_children = []
        global_child_counter = 1
        for dl_chunk in base_chunks:
            raw_text = active_chunker.contextualize(chunk=dl_chunk)
            if not raw_text.strip():
                continue

            page_numbers = set()
            headings_path = []
            extracted_footnotes = []
            main_chapter = "Hauptdokument"
            
            for source_item in dl_chunk.meta.doc_items:
                if hasattr(source_item, "prov") and source_item.prov:
                    for p in source_item.prov:
                        page_numbers.add(p.page_no)
                try:
                    path_nodes = doc.get_heading_path(item=source_item)
                    if path_nodes:
                        headings_path = [node.text for node in path_nodes if hasattr(node, "text")]
                        if len(headings_path) > 0:
                            main_chapter = headings_path[0] 
                except Exception:
                    pass
                
                if source_item.label == "footnote" and hasattr(source_item, "text"):
                    extracted_footnotes.append(source_item.text)

            child_text_lines = []
            if headings_path:
                child_text_lines.append(f"Kontext: {' > '.join(headings_path)}\n")
            child_text_lines.append(raw_text)
            
            if extracted_footnotes:
                child_text_lines.append("\n[Anmerkungen / Fußnoten im Abschnitt]:")
                for fn in extracted_footnotes:
                    child_text_lines.append(f"- {fn}")
            
            final_child_text = "\n".join(child_text_lines)
                    
            # HARTER CHECK: Wenn das CHILD das Limit des Embedders sprengt
            child_tokens = tokenizer.encode(final_child_text, add_special_tokens=False)
            exact_child_token_count = len(child_tokens) # OPTIMIERT: Wert direkt sichern
            
            if exact_child_token_count > max_model_length:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Kritischer Fehler: Ein einzelnes Child-Element überschreitet das "
                           f"Modell-Limit ({exact_child_token_count} > {max_model_length})."
                )

            prepared_children.append({
                "dl_chunk_obj": dl_chunk,
                "final_child_text": final_child_text,  # OPTIMIERT: Variable wiederverwenden statt neu joinen
                "headings": headings_path if headings_path else ["Hauptdokument"],
                "main_chapter": main_chapter,
                "page_numbers": sorted(list(page_numbers)),
                "global_index": global_child_counter,
                "exact_token_count": exact_child_token_count # OPTIMIERT: Für Schritt 2 bereitstellen
            })
            global_child_counter += 1

        # 2. Schritt: Sliding Window & Normalisierte Trennung
        output_parents = []
        output_children = []
        exported_child_indices = set()
        
        total_children = len(prepared_children)
        window_size = request.config.max_child_chunks_per_parent
        overlap = request.config.parent_overlap_chunks
        
        current_parent_index = 1
        i = 0

        while i < total_children:
            current_window = []
            start_child = prepared_children[i]
            current_chapter = start_child["main_chapter"]
            
            for j in range(i, min(i + window_size, total_children)):
                candidate_child = prepared_children[j]
                if candidate_child["main_chapter"] != current_chapter:
                    break
                current_window.append(candidate_child)

            if not current_window:
                break

            # Metadaten einsammeln
            parent_page_numbers = set()
            for child in current_window:
                parent_page_numbers.update(child["page_numbers"])
            
            # Wir holen den echten, unberührten Reintext aus jedem Docling-Chunk-Objekt
            raw_text_blocks = [child["dl_chunk_obj"].text for child in current_window if child["dl_chunk_obj"].text]
            
            # Formatiere das Kapitel: Hauptüberschrift als H1 oben drüber, dann der Fließtext
            if current_chapter != "Hauptdokument":
                parent_text = f"# {current_chapter}\n\n" + "\n\n".join(raw_text_blocks)
            else:
                parent_text = "\n\n".join(raw_text_blocks)         
            
            # Tokenanzahl bestimmen
            tokens = tokenizer.encode(parent_text, add_special_tokens=False)
            token_count = len(tokens)
            
            if token_count > max_model_length:
                logger.info(
                    f"Parent {current_parent_index} hat ({token_count} Tokens). "
                    f"Text wird vollständig übernommen."
                )

            src_path = request.source_path
            parent_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{src_path}_parent_{current_parent_index}"))

            output_parents.append({
                "id": parent_uuid,
                "text": parent_text,
                "meta": {
                    "heading": current_chapter,
                    "headings": current_window[0]["headings"],
                    "page_numbers": sorted(list(parent_page_numbers)),
                    "source_path": request.source_path,
                    "token_estimate": token_count
                }
            })

            for child_idx, child in enumerate(current_window):
                g_idx = child["global_index"]
                if g_idx in exported_child_indices:
                    continue
                exported_child_indices.add(g_idx)
                
                child_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{src_path}_child_{g_idx}"))
                
                output_children.append({
                    "id": child_uuid,
                    "parent_id": parent_uuid,
                    "text": child["final_child_text"],
                    "meta": {
                        "headings": child["headings"],
                        "page_numbers": child["page_numbers"],
                        "source_path": request.source_path,
                        "token_estimate": child["exact_token_count"]  # OPTIMIERT: 100% exakter Wert ohne .split()
                    }
                })

            actual_processed = len(current_window)
            next_global_idx = i + actual_processed
            
            if next_global_idx < total_children and prepared_children[next_global_idx]["main_chapter"] != current_chapter:
                i = next_global_idx
            else:
                step = max(1, window_size - overlap)
                if actual_processed < window_size:
                    i += actual_processed
                else:
                    i += step
            
            current_parent_index += 1

        # 3. Schritt: Persistierung der sauberen, getrennten Listen
        base_path, _ = os.path.splitext(request.json_path)
        chunks_output_path = f"{base_path}.chunks.json"

        response_payload = {
            "parents": output_parents,
            "children": output_children,
            "metadata": {
                "total_parents": len(output_parents),
                "total_children": len(output_children),
                "tokenizer": request.config.tokenizer_name
            }
        }

        with storage.open(chunks_output_path, mode="w") as f:
            json.dump(response_payload, f, ensure_ascii=False, indent=2)

        logger.info(f"Normalisierte Chunks erfolgreich exportiert: {chunks_output_path}")
        return response_payload

    except Exception as e:
        logger.error(f"Fehler beim normalisierten Hierarchie-Chunking: {e}")
        raise HTTPException(status_code=500, detail=str(e))
            
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8889)
