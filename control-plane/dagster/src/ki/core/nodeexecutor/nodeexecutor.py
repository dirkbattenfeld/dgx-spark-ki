# ki/core/nodeexecutor/nodeexecutor.py

from ki.core.nodeexecutor.dataclasses import NodeConfig, NodeOverrides
from ki.core.nodeexecutor.dataclasses import UpstreamData
from ki.core.nodeexecutor.noderesultprojector import NodeResultProjector

from ki.core.base.logging import configure_logger
from ki.core.pipelineorchestrator.pipelineorchestrator import PipelineOrchestrator

from pathlib import Path
import logging
from typing import Optional, Any, Type, List
from pydantic import BaseModel


class NodeExecutor:
    """
    Nimmt ggfs. upstream Data und node_config_overrides von Dagster entgegen.
    Merged die Overrides in die NodeConfig.
    Startet den PipelineOrchestrator mit der NodeConfig und reicht Upstream Data weiter.
    Erzeugt die NodeResults und gibt sie zurück. 
    """

    @staticmethod
    def crawl_dataclass(obj: Any, search_class: Type) -> List[Any]:
        found_elements = []

        # 1. Direkter Treffer
        # WICHTIG: Falls search_class über verschiedene Wege importiert wurde,
        # kann isinstance fehlschlagen. Wir prüfen zur Not auch den Namen.
        if isinstance(obj, search_class):
            return [obj]

        # 2. Listen, Sets, Tuples (Iterables)
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                found_elements.extend(NodeExecutor.crawl_dataclass(item, search_class))

        # 3. Dictionaries
        elif isinstance(obj, dict):
            for value in obj.values():
                found_elements.extend(NodeExecutor.crawl_dataclass(value, search_class))

        # 4. Objekte (Pydantic, Dataclasses, reguläre Klassen)
        elif hasattr(obj, "__dict__") or isinstance(obj, BaseModel):
            # Falls es ein Pydantic-Modell ist, nutzen wir model_fields
            if isinstance(obj, BaseModel):
                fields = obj.model_fields.keys()
            else:
                # Für normale Objekte nutzen wir __dict__
                fields = vars(obj).keys()

            for field_name in fields:
                try:
                    field_value = getattr(obj, field_name)
                    found_elements.extend(NodeExecutor.crawl_dataclass(field_value, search_class))
                except (AttributeError, TypeError):
                    continue
                    
        return found_elements

    def __init__(
        self,
        node: NodeConfig,
        dagster_context: Optional[Any] = None,
        upstream_data: UpstreamData = None
        ):
        """
        Args:
            node (NodeConfig): Node-Konfigurationen.
        """   
        
        # Übergebene NodeConfig aus yaml
        self.config_node = node
        self.context = dagster_context
        self.upstream_data = upstream_data
        
        # Nach Node Overrides in Upstream Daten suchen
        overrides = NodeExecutor.crawl_dataclass(
            obj=self.upstream_data, 
            search_class=NodeOverrides
        )
        overrides_found = len(overrides)   
        fan_idx = self.config_node.fan_index or 0 # Fallback auf 0

        # Initialisierung der Tracking-Variablen für das Logging
        used_node_id = self.config_node.node_id
        used_node_name = getattr(self.config_node, "name", "N/A")

        # Logik-Mapping
        if fan_idx == 0:
            if overrides_found == 0:
                # Die NodeConfig aus yaml mergen, kein Fan out
                self.node = self.config_node
            else:
                # Kein Fan-out, aber mindestens ein Override kommt aus den Upstream Daten
                # Override 0 wird gemergt
                override = overrides[0]
                used_node_id = override.node_id
                used_node_name = override.name
                # Update der Config mit Override-Daten
                self.node = self.config_node.model_copy(update=override.model_dump(exclude_unset=True))
        else:
            # Fan-out Logik
            if overrides_found > 0:
                # Passendes Override selektieren
                override_index = (fan_idx - 1) % overrides_found
                base_override = overrides[override_index]
            else:
                # Config selektieren für fan-out
                base_override = self.config_node

            current_override = base_override.model_copy(deep=True)
            # Eindeutige ID für Fan-out erzeugen
            used_node_id = f"{current_override.node_id}_{fan_idx:02d}"
            used_node_name = getattr(current_override, "name", "N/A")
            
            # Wichtig: Die ID im Override setzen, bevor gemergt wird
            current_override.node_id = used_node_id
            used_node_name = current_override.name
            self.node = self.config_node.model_copy(
                update=current_override.model_dump(exclude_unset=True)
            )

        # Basis- und Log-Pfade
        self.node_id = self.node.node_id
        self.base_path = Path(self.node.base_path)
        self.config_path = self.base_path / self.node.config_path
        self.build_log_path = self.base_path / self.node.build_log_path
        self.run_log_path = self.base_path / self.node.run_log_path

        # Logger konfigurieren
        self.build_logger = configure_logger(
            name=f"Build.{self.node_id}",
            log_dir=self.build_log_path,
            file_level=logging.INFO,
            console_level=logging.INFO,
            file_prefix="build"
        )

        self.run_logger = configure_logger(
            name=f"Run.{self.node_id}",
            log_dir=self.run_log_path,
            file_level=logging.INFO,
            console_level=logging.INFO,
            file_prefix="run",
            dagster_context=dagster_context
        )

        self.build_logger.info(f"DEBUG (NodeExecutor): {str(upstream_data)}")
        for i in range(overrides_found):
            self.build_logger.info(f"DEBUG (NodeExecutor): {i} ... {overrides[i].node_id} ... {overrides[i].name}")
        
        if overrides_found == 0:
            self.build_logger.info(f"NodeExecutor({self.node_id}): Kein Node Override in Upstream-Daten gefunden. Nutze statische Config.")

        else:
            self.build_logger.info(f"NodeExecutor({self.node_id}): {overrides_found} Node Overrides in Upstream Daten entdeckt. Genutzt wird die NodeId {used_node_id} mit dem Namen {used_node_name}")

        # Orchestrator vorbereiten
        self.orchestrator = PipelineOrchestrator(
            node_id=self.node_id,
            config_path=self.config_path,
            base_path=self.base_path,
            build_logger=self.build_logger,
            run_logger=self.run_logger,
            generator_name=self.node.generator_name,
            generator_config=self.node.generator_config,
            upstream_data=self.upstream_data
        )

    def run(self):
        """
        Führt die Build-Phase, die Pipeline-Initialisierung und die Run-Phase aus.

        Returns:
            Ergebnisse der Run-Phase (Dict mit NodeResults)
        """

        self.build()
        self.initialize_pipeline()

        orchestrator_result=self.execute_run()

        projector = NodeResultProjector(sep="/", blacklist = ["run_id", "executor_status", "write_artifact"])
        
        return {
        "raw": {
            "result": orchestrator_result,
            "config": self.node
        },
        "structured": projector.project(orchestrator_result) 
        }
    
    
    # --- interne Helfer ---
    def build(self):
        """Führt die Build-Phase des Orchestrators aus."""
        self.build_logger.info("Starting build phase...")
        self.orchestrator.build()
        self.build_logger.info("Build phase completed.")

    def initialize_pipeline(self):
        """Initialisiert die Pipeline im Orchestrator."""
        self.build_logger.info("Initializing pipeline...")
        self.orchestrator.initialize_pipeline()
        self.build_logger.info("Pipeline initialized.")

    def execute_run(self):
        """Führt die Run-Phase aus und gibt die Ergebnisse zurück."""
        self.run_logger.info("Starting run phase...")
        results = self.orchestrator.run()
        self.run_logger.info("Run phase completed.")
        return results
    