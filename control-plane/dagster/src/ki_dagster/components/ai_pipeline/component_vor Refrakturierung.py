import dagster as dg
from dagster.components import Component, Resolvable, ComponentLoadContext

from dataclasses import dataclass
from typing import Any, List, Dict
from pydantic import BaseModel

from ki.core.nodeexecutor.dataclasses import UpstreamData, UpstreamNodeData
from ki.core.nodeexecutor.nodeexecutor import NodeExecutor
from ki_dagster.components.ai_pipeline.dagstermetadatafactory import DagsterMetaDataFactory
from ki.core.nodeexecutor.dataclasses import NodeConfig 


@dataclass
class AIPipelineComponent(Component, Resolvable):
    nodes: List[dict]
 
    @staticmethod
    def collect_overrides_recursive(obj: Any) -> List[Any]:
        found_overrides = []

        # 1. Listen-Handling 
        if isinstance(obj, list):
            for item in obj:
                found_overrides.extend(AIPipelineComponent.collect_overrides_recursive(item))

        # 2. DICT-HANDLING 
        elif isinstance(obj, dict):
            # Check: Ist der Key direkt in diesem Dict?
            if "override_node_configs" in obj:
                val = obj["override_node_configs"]
                if isinstance(val, list):
                    found_overrides.extend(val)
            
            # Trotzdem tiefer graben, falls verschachtelt
            for value in obj.values():
                found_overrides.extend(AIPipelineComponent.collect_overrides_recursive(value))

        # 3. BASEMODEL-HANDLING (Pydantic)
        elif isinstance(obj, BaseModel):
            # Attribut-Check
            if hasattr(obj, 'override_node_configs'):
                val = getattr(obj, 'override_node_configs')
                if isinstance(val, list):
                    found_overrides.extend(val)
            
            # Rekursion über alle Felder
            for field_name in obj.model_fields:
                field_value = getattr(obj, field_name)
                found_overrides.extend(AIPipelineComponent.collect_overrides_recursive(field_value))
                
        return found_overrides


    def build_defs(self, context: ComponentLoadContext) -> dg.Definitions:
        assets = []
        for node in self.nodes:
            raw_deps = node.get("deps") or []
            
            # Wir nutzen einfach die node_id als direkten Asset-Key.
            # Der Key im Dict (links) ist der Name des Arguments in der _asset Funktion.
            # In der build_defs:
            ins = {
                dep_id: dg.AssetIn(key=dep_id) 
                for dep_id in raw_deps
            }
                   
            assets.append(self._create_asset(node, ins))
            
        return dg.Definitions(assets=assets)

    def _create_asset(self, node: dict, ins: Dict[str, dg.AssetIn]):
        node_id = node.get("node_id")
        node_name = node.get("name", node_id) # Name nur für Logs/Anzeige

        @dg.asset(
            name=node_id,  # Die node_id IST der Asset-Name
            ins=ins,
            description=f"Pipeline Node: {node_name}" # Der Name landet in der Beschreibung
        )
        def _asset(context: dg.AssetExecutionContext, **kwargs):
            # kwargs enthält nun direkt { "node_id_vorgänger": ergebnis }
            context.log.info(f"Starte Ausführung von {node_name} ({node_id})")
            validated_node = NodeConfig.model_validate(node)

            # Kwargs in UpstreamData umwandeln
            upstream_nodes = []
            for val in kwargs.values():
                if isinstance(val, dict) and "result" in val:
                    upstream_nodes.append(
                        UpstreamNodeData(
                            result=val["result"],
                            node_config=val["config"]
                        )
                    )
        
            # PipelineInput Container erstellen
            upstream_data = UpstreamData(nodes=upstream_nodes)

            executor = NodeExecutor(
                node=validated_node, 
                dagster_context=context,
                upstream_data=upstream_data
            )
            execution_result = executor.run()

            # Alle Overrides extrahieren
            result = execution_result["raw"]["result"]
            context.log.info(f"Vor Override Injektion: {execution_result['raw']}")
            
            all_overrides = AIPipelineComponent.collect_overrides_recursive(result)            
            context.log.info(f"Overrides Crawler fertig. Gefundene Overrides: {len(all_overrides)}")
            execution_result["raw"]["override_node_configs"] = all_overrides
            context.log.info(f"Nach Override Injektion: {execution_result['raw']}")
            
            # Inspektion und Vorbereitung des Dynamic Outputs
            for index, override in enumerate(all_overrides):
                # Wir generieren einen eindeutigen Key für Dagster
                base_id = getattr(override, "node_id", f"node_{index}")
                mapping_key = f"{base_id.replace('-', '_')}_generated"

                # Log-Inspektion
                context.log.info(
                    f"PROLOG: DynamicOutput bereit für Key: {mapping_key} "
                    f"mit Payload-Typ: {type(override).__name__}"
                )

            # Factory-Aufruf
            is_multi_trial = isinstance(execution_result["raw"], list) and len(execution_result["raw"]) > 1            
            business_meta = DagsterMetaDataFactory.create(
                structured_data=execution_result["structured"], 
                aggregate=is_multi_trial
            )                                  
                      
            tech_meta = {
                "node_type": dg.MetadataValue.text(node.get("type")),
                "executor_status": dg.MetadataValue.text("success"),
                "run_id": dg.MetadataValue.text(context.run_id),
                "overrides_found": dg.MetadataValue.int(len(all_overrides))
            }

            # 3. Finaler Dagster-Output
            return dg.Output(
                value=execution_result["raw"], # Das Pydantic-Objekt für nächsten Node
                metadata={**tech_meta, **business_meta}
            )
        
        return _asset