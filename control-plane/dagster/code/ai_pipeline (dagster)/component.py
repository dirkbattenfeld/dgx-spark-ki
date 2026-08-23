import dagster as dg
from dataclasses import dataclass
from typing import List, Dict
from dagster.components import Component, Resolvable, ComponentLoadContext

# WICHTIG: Dein Framework importieren (muss im sys.path sein)
from ki.core.nodeexecutor.nodeexecutor import NodeExecutor
from ki.core.nodeexecutor.dataclasses import NodeConfig

@dataclass
class AIPipelineComponent(Component, Resolvable):
    nodes: List[dict]

    def build_defs(self, context: ComponentLoadContext) -> dg.Definitions:
        assets = []
        for node in self.nodes:
            # Wir binden das aktuelle 'node' Dictionary fest an das Asset
            assets.append(self._create_asset(node))
        return dg.Definitions(assets=assets)

    def _create_asset(self, node: dict):
        node_name = node.get("name")
        node_id = node.get("node_id")

        # Wir speichern die Daten lokal für die Asset-Funktion
        node_config = dict(node)

        @dg.asset(name=node_name, key_prefix=[node_id])
        def _asset(context: dg.AssetExecutionContext):
            context.log.info(f"--- STARTE NODE EXECUTOR: {node_name} ---")

            validated_node = NodeConfig.model_validate(node_config)

            # HIER passiert der Aufruf deines Frameworks:
            try:
                # Wir übergeben die Config aus der YAML an deinen Executor
                executor = NodeExecutor(validated_node, dagster_context=context)

                # Der eigentliche Lauf (hier entstehen deine Logs/Files)
                executor.run()

                context.log.info(f"--- NODE {node_name} ERFOLGREICH BEENDET ---")
            except Exception as e:
                context.log.error(f"Fehler im NodeExecutor für {node_name}: {str(e)}")
                raise e

        return _asset

