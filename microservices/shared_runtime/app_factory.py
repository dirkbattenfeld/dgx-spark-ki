# microservices/shared_runtime/app_factory.py
import json
from fastapi import FastAPI, Body
from typing import Dict, Any, Callable
from pydantic import BaseModel
from libs.streampipe.single_runner import SinglePipelineRunner

def create_generic_service(
    title: str,
    topology_factory: Callable[[], SinglePipelineRunner],
    transform_factory: Callable[[Dict[str, BaseModel]], Dict[str, Any]]
) -> FastAPI:
    """
    Erzeugt eine vollkommen agnostische FastAPI-Instanz.
    Fachlogik und Mapper werden von außen injiziert.
    """
    app = FastAPI(title=title)

    # Die Topologie einmalig für diesen Container instanziieren
    runner = topology_factory()

    @app.post("/v1/execute")
    async def execute_pipeline(
        payload: Dict[str, Any] = Body(..., description="Der kompakte, vom SDK vorstrukturierte Payload")
    ):
        print("DEBUG (app_factory) Inital Payload: \n")
        print(json.dumps(payload, indent=4, ensure_ascii=False))
        print(20*"-")
               
        # Extraktion der Overrides auf HTTP-Grenzschicht (Schnittstelle)
        overrides = payload.pop("overrides", None)
        
        if "payload" in payload and isinstance(payload["payload"], dict):
            inner_payload = payload.pop("payload")
            payload.update(inner_payload)

        # DEBUG: Schau dir kurz an, was nach dem Flachklopfen wirklich ankommt
        print("DEBUG (app_factory) Final Overrides: \n")
        print(json.dumps(overrides, indent=4, ensure_ascii=False))
        print(20*"-")
        print("DEBUG (app_factory) Final Payload: \n")
        print(json.dumps(payload, indent=4, ensure_ascii=False))
        print(20*"-")
           
        # Daten und Steuerbefehle sauber getrennt an den Runner übergeben
        pool = await runner.run(initial_payload=payload, overrides=overrides)
                
        # Den Pool durch die injizierte Fach-Transformationsfunktion jagen
        raw_response = transform_factory(pool)
        
        return raw_response

    return app

