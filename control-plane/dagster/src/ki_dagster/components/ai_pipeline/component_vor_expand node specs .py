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
            ins = {dep_id: dg.AssetIn(key=dep_id) for dep_id in raw_deps}
            assets.append(self._create_asset_definition(node, ins))
        return dg.Definitions(assets=assets)

    def _create_asset_definition(self, node: dict, ins: Dict[str, dg.AssetIn]) -> dg.AssetsDefinition:
        node_id = node.get("node_id")
        node_name = node.get("name", node_id)

        @dg.asset(name=node_id, ins=ins, description=f"Pipeline Node: {node_name}")
        def _asset(context: dg.AssetExecutionContext, **kwargs):
            # 1. INPUT: Kwargs -> UpstreamData
            upstream_data = self._resolve_inputs(kwargs)
            
            # 2. EXECUTION: Business Logic
            execution_result = self._execute_node(node, context, upstream_data)
            
            # 3. OVERRIDES: Extraktion & Mapping Keys
            all_overrides = self._extract_and_map_overrides(execution_result, context)
            
            # 4. METADATA: Business & Tech Meta
            metadata = self._generate_metadata(node, context, execution_result, all_overrides)

            # 5. OUTPUT: Finaler Return (noch statisch als "Klumpen")
            return self._send_output(execution_result, metadata)

        return _asset

    def _resolve_inputs(self, kwargs: Dict[str, Any]) -> UpstreamData:
        upstream_nodes = []
        for val in kwargs.values():
            # Falls Upstream ein Dictionary mit "result" ist (Standard)
            if isinstance(val, dict) and "result" in val:
                upstream_nodes.append(UpstreamNodeData(result=val["result"], node_config=val["config"]))
        return UpstreamData(nodes=upstream_nodes)

    def _execute_node(self, node: dict, context: dg.AssetExecutionContext, upstream_data: UpstreamData) -> Dict[str, Any]:
        validated_node = NodeConfig.model_validate(node)
        executor = NodeExecutor(node=validated_node, dagster_context=context, upstream_data=upstream_data)
        return executor.run()

    def _extract_and_map_overrides(self, execution_result: Dict[str, Any], context: dg.AssetExecutionContext) -> List[Any]:
        """Extrahiert Overrides und bereitet Mapping-Keys vor."""
        raw_data = execution_result["raw"]
        # Wir suchen tief im Resultat nach Overrides
        all_overrides = self.collect_overrides_recursive(raw_data)
        
        context.log.info(f"Asset Factory: Overrides Crawler hat {len(all_overrides)} Node Overrides gefunden.")
        
        # Mapping Key Logik (Vorbereitung für Dynamic Output)
        for index, override in enumerate(all_overrides):
            # Nutze node_id des Overrides oder Fallback
            base_id = getattr(override, "node_id", f"node_{index+1}")
            # Eindeutiger 3-stelliger Key: node_001_generated
            mapping_key = f"{base_id.replace('-', '_')}_{index+1:03d}_generated"
            
            # Hier setzen wir den Key temporär am Objekt, damit der Downstream ihn kennt
            setattr(override, "_dagster_mapping_key", mapping_key)
            
            context.log.info(f"Asset Factory: Override für nächsten Node vorbereitet mit Key: {mapping_key} für {type(override).__name__}")

        # Injektion in das Hauptresultat (dein bisheriger "Klumpen")
        if isinstance(raw_data, dict):
            raw_data["override_node_configs"] = all_overrides
            
        return all_overrides

    def _generate_metadata(self, node: dict, context: dg.AssetExecutionContext, 
                           execution_result: Dict[str, Any], overrides: List[Any]) -> Dict[str, Any]:
        is_multi_trial = isinstance(execution_result["raw"], list) and len(execution_result["raw"]) > 1            
        business_meta = DagsterMetaDataFactory.create(
            structured_data=execution_result["structured"], 
            aggregate=is_multi_trial
        )                                  
        tech_meta = {
            "node_type": dg.MetadataValue.text(node.get("type")),
            "executor_status": dg.MetadataValue.text("success"),
            "run_id": dg.MetadataValue.text(context.run_id),
            "overrides_found": dg.MetadataValue.int(len(overrides))
        }
        return {**tech_meta, **business_meta}

    def _send_output(self, execution_result: Dict[str, Any], metadata: Dict[str, Any]) -> dg.Output:
        """Versendet das Ergebnis."""
        return dg.Output(
            value=execution_result["raw"],
            metadata=metadata
        )
