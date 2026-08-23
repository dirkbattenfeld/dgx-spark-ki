import logging
import asyncio
import threading
import uvicorn
import uuid
from fastapi import FastAPI
from typing import Any, Dict, Generator, List

from ki.core.pipelineorchestrator.generator.base import BaseRunGenerator, RunOverrides
from ki.core.pipelineorchestrator.generator.registry import generator_registry

@generator_registry.register("fastapi_endpoint")
class FastApiRunGenerator(BaseRunGenerator):
    ExpectsFeedback: bool = True
    
    def __init__(self,
                 mapping: List[Dict[str, Any]],
                 logger: logging.Logger,
                 host: str = "0.0.0.0",
                 port: int = 8000
                 ):
        self.mapping = mapping
        self.logger = logger
        self.host = host
        self.port = port
        self.should_exit = asyncio.Event()
        self.app = FastAPI()
        self._input_queue = asyncio.Queue(maxsize=1)
        self.server_loop = asyncio.new_event_loop() # Loop hier festlegen
        self._setup_routes()
        self._start_background_server()
        self._pending_responses: Dict[str, asyncio.Future] = {}

    def _setup_routes(self):
        @self.app.post("/trigger")
        async def trigger(payload: Dict[str, Any]):
            # 1. Eindeutige ID für diesen Request erstellen
            request_id = str(uuid.uuid4())
            loop = asyncio.get_running_loop()
            
            # 2. Ein Future erstellen, das später vom Generator gefüllt wird
            future = loop.create_future()
            self._pending_responses[request_id] = future
            
            # 3. Payload mit ID in die Queue legen
            payload["_request_id"] = request_id
            await self._input_queue.put(payload)
            
            self.logger.info(f"Request {request_id} empfangen und in Queue eingereiht.")

            try:
                # 4. Hier wartet FastAPI, bis das Ergebnis da ist (Timeout 60s)
                result = await asyncio.wait_for(future, timeout=60.0)
                return result
            except asyncio.TimeoutError:
                return {"error": "Pipeline timeout"}
            finally:
                self._pending_responses.pop(request_id, None)

        @self.app.post("/shutdown")
        async def shutdown():
            self.server_loop.call_soon_threadsafe(self.should_exit.set)
            return {"status": "shutting down..."}


    def _start_background_server(self):
        # Der Thread nutzt den bereits in __init__ erstellten Loop
        thread = threading.Thread(
            target=lambda: self.server_loop.run_until_complete(self._run_server()), 
            daemon=True
        )
        thread.start()


    async def _run_server(self):
        # log_level auf "info" für Sichtbarkeit
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)

        # Wir überschreiben die Standard-Serve-Logik, um auf unser Event zu hören
        async def serve_until_stopped():
            server_task = asyncio.create_task(server.serve())
            await self.should_exit.wait()
            server.should_exit = True
            await server_task

        await serve_until_stopped()

        
    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.Logger) -> "FastApiRunGenerator":
        return cls(
            mapping=config.get("mapping", []),
            logger=logger,
            host=config.get("host", "0.0.0.0"),
            port=config.get("port", 8000)
        )   
        
    
    def process_feedback(self, result: Any) -> Any:
        if hasattr(result, "component_results") and len(result.component_results) > 0:
            # Greife das letzte Element der Liste
            last_component = result.component_results[-1]
            
            # Gib eine kompakte Version zurück
            return {
                "run_id": getattr(result, "run_id", "unknown"),
                "component": last_component.component_id,
                "results": last_component.outputs_summary
            }
        # Fallback, falls die Liste leer ist
        return result
    
    
    def _apply_mapping(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        overrides = {}
        for item in self.mapping:
            val = payload.get(item["payload_key"])
            if val is None: continue
            
            if "suffix" in item:
                val = f"{val}{item['suffix']}"

            comp_name, attr_name = item["target"]
            if comp_name not in overrides:
                overrides[comp_name] = {}
            overrides[comp_name][attr_name] = val
        return overrides
    
 
    def generate(self) -> Generator[RunOverrides, None, None]:
        while True:
            # Warte auf neuen Input aus dem HTTP-Endpunkt
            future = asyncio.run_coroutine_threadsafe(
                self._input_queue.get(), 
                self.server_loop
            )
            
            payload = future.result()
            request_id = payload.get("_request_id") # ID aus dem Request

            # A) Overrides generieren und an Orchestrator senden
            overrides = self._apply_mapping(payload)
            
            # B) Hier pausiert der Generator und wartet auf das .send(result) vom Orchestrator
            pipeline_result = yield overrides
            
            # C) Das Ergebnis an das wartende HTTP-Future im server_loop zurückgeben
            if request_id and request_id in self._pending_responses:
                self.logger.info(f"Sende Ergebnis für Request {request_id} an FastAPI zurück.")
                self.server_loop.call_soon_threadsafe(
                    self._pending_responses[request_id].set_result, 
                    pipeline_result
                )
