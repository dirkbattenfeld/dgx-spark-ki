# libs/streampipe/runner.py
import asyncio
import uuid
from typing import List, Type, Union, Dict, Any
from pydantic import BaseModel

from applications.rag.pipelines.rag_ingestion.steps.models import ExtractInput
from libs.streampipe.basemodels import BasePipelineEnv
from libs.streampipe.step import PipelineStep

class PipelineRunner:
    """
    Verwaltet das asynchrone Streaming von Dokumenten durch eine Kette
    von beliebig vielen PipelineSteps.
    """
    def __init__(
        self, 
        steps: List[PipelineStep], 
        env: BasePipelineEnv,
        initial_input_class: Type[BaseModel] = ExtractInput,
        input_field_name: str = "source_path"
    ):
        self.steps = steps
        self.env = env
        self.initial_input_class = initial_input_class
        self.input_field_name = input_field_name
        
        self.clients_dict = {
            "docling_client": getattr(self.env, "docling_client", None),
            "vllm_client": getattr(self.env, "vllm_client", None),
            "infinity_client": getattr(self.env, "infinity_client", None),
            "qdrant_service": getattr(self.env, "qdrant_client", None),
            "storage_client": getattr(self.env, "storage_client", None)
        }
        
    async def _stream_document(self, run_id: str, global_payload: Dict[str, Any]):
        """Reicht die instanziierten Datenklassen linear weiter."""
        async with self.env.doc_semaphore:
            info_val = next(iter(global_payload.values())) if global_payload else "No Payload"
            print(f" ⚙️ Stamm-Prozess für [{run_id}] gestartet ({info_val})")
            
            try:
                current_data = self.initial_input_class(**global_payload)
            except Exception as e:
                print(f"💥 Fehler bei der Instanziierung von {self.initial_input_class.__name__}: {e}")
                return
                       
            for step in self.steps:
                try:
                    # Step Execution (Nutzt das im Konstruktor hinterlegte self.clients_dict)
                    current_data = await step.execute(
                        input_data=current_data, 
                        global_payload=global_payload, 
                        clients=self.clients_dict
                    )
                    
                    # Step Postprocess
                    current_data = step.postprocess(run_id, current_data, global_payload)
                    
                    status = getattr(current_data, "status", "success")
                    if status in ("error", "failed"):
                        print(f"🛑 Abbruch der Pipeline für Run: '{run_id}' wegen Fehler in Schritt '{step.name}'.")
                        break
                        
                except Exception as e:
                    print(f"💥 Kritischer Fehler in Step '{step.name}' für Run: '{run_id}': {e}")
                    break
                    
    async def run(self, inputs: Union[List[str], List[Dict[str, Any]]]):
        """Feuert alle Dokumente/Requests parallel an (Streaming-Logik)."""
        tasks = []
        for item in inputs:
            run_id = f"run_{uuid.uuid4().hex[:8]}"
            
            if isinstance(item, str):
                global_payload = {self.input_field_name: item}
            elif isinstance(item, dict):
                global_payload = item
            else:
                raise ValueError("Pipeline-Input must be a string or a dictionary.")
                
            tasks.append(self._stream_document(run_id, global_payload))
        
        await asyncio.gather(*tasks, return_exceptions=True)
