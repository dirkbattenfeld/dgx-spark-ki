# ki/core/pipelineresult/pipelineresultpolicy.py

from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext, RunMetaData

from dataclasses import dataclass, field
from typing import List

@dataclass
class PersistAction:
    """Definiert einen einzelnen Persistierungsschritt"""
    projector_key: str
    flattener_key: str
    serializer_key: str
    writer_key: str
    writer_kwargs: dict = field(default_factory=dict)

@dataclass
class PolicyOutput:
    """Das Ergebnis der Policy-Entscheidung"""
    action_set: List[PersistAction]
    return_level: str

class PipelineResultPolicy:
    def __init__(self, global_run_ctx: GlobalRunContext):
        self.global_run_ctx = global_run_ctx

    def resolve(self, run_metadata: RunMetaData) -> PolicyOutput:
        # Hier findet später die Logik statt.
        # Jetzt erst mal fest verdrahtet (Mock):
        actions = [
            PersistAction(
                projector_key="results",   # Holt alle Attribute
                flattener_key="standard",    # Macht Pydantic flach
                serializer_key="json",       # Wandelt in JSON-String
                writer_key="console"         # print()
            ),
            PersistAction(
                projector_key="results",
                flattener_key="standard",
                serializer_key="json",
                writer_key="file",
                writer_kwargs={"filename": "run_summary.json"} 
            ),
            PersistAction(
                projector_key="complete",
                flattener_key="standard",
                serializer_key="json",
                writer_key="file",
                writer_kwargs={"filename": "run_summary_complete.json"} 
            )
        ]

        return PolicyOutput(
            action_set=actions,
            return_level="results"
        )
