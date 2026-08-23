# ki/core/pipelineorchestrator/globalruncontextfactory.py

from ki.core.base.logging import ContextLoggerAdapter
from ki.core.datapipeline.datapipeline_dataclasses import GlobalBuildContext, GlobalRunContext
from ki.artifactstore.serializer.registry import serializer_registry
from ki.artifactstore.artifactstore import ArtifactStore, PathResolver
from ki.core.pipelineresult.projector.registry import projector_registry
from ki.core.pipelineresult.flattener.registry import flattener_registry
from ki.core.pipelineresult.writer.registry import writer_registry
from ki.bootstrap import infra_settings

from dataclasses import fields
from pathlib import Path
import logging
from typing import Any, Dict, Callable, Optional, Tuple
import re


class GlobalRunContextFactory:
    """
    Baut GlobalRunContext aus:
      - base_path aus global_build_ctx
      - run_path dynamisch generiert über eine Funktion
      - verbose aus YAML (optional Override)
    
    Regeln:
      - base_path darf nicht aus YAML kommen (Warnung)
      - nur erlaubte Keys werden akzeptiert
    """

    def __init__(
        self,
        global_build_ctx: GlobalBuildContext,
        node_id: str,
        yaml_global: Optional[Dict[str, Any]],
        logger: logging.Logger,
        *,
        run_dir_fn: Optional[Callable[[Path], Path]] = None,
    ):
        self.global_build_ctx = global_build_ctx
        self.node_id = node_id
        self.yaml_global = yaml_global or {}
        self.logger = logger # wird überschrieben durch den Run_Logger in pipeline.run
        
        # --- Allowed keys in YAML ---
        self._allowed_keys = {
            f.name for f in fields(GlobalRunContext)
            if f.name not in {"logger"}
        }

        # --- Funktion zur Erzeugung von run_path ---
        # Default-Funktion, falls keine injiziert wird
        self.run_dir_fn = run_dir_fn or self._default_run_dir

        # Warnung, falls YAML base_path setzt
        if "base_path" in self.yaml_global:
            self.logger.warning(
                "YAML 'global' Abschnitt enthält 'base_path', "
                "dieser wird ignoriert und durch global_build_ctx.base_path ersetzt."
            )

    # -------- Public API --------

    def create(self, logger: logging.Logger) -> GlobalRunContext:
        self._validate_keys()
        # base_path kommt ausschließlich aus dem global_build_ctx
        base_path = self.global_build_ctx.base_path
        # run_path wird dynamisch erzeugt über injizierte oder Default-Funktion
        run_path, run_id = self.run_dir_fn(base_path, self.node_id)    
        # logger mit Run Context anreichern
        run_logger = ContextLoggerAdapter(logger, run_id=run_id)
        # verbose kann aus YAML überschreiben, Default=False
        verbose = bool(self.yaml_global.get("verbose", False))
        # Artifact Store bauen 
        artifact_store = ArtifactStore(
            serializer_registry=serializer_registry,
            path_resolver=PathResolver(),
            logger=logger)
        
        return GlobalRunContext(
            run_id=run_id,
            base_path=base_path,
            run_path=run_path,
            artifact_store=artifact_store,
            serializer_registry=serializer_registry,
            projector_registry=projector_registry,
            flattener_registry=flattener_registry,
            writer_registry=writer_registry,
            infra=infra_settings,
            run_logger=run_logger,
            verbose=verbose,
        )

    # -------- Validation --------

    def _validate_keys(self) -> None:
        unknown = set(self.yaml_global) - self._allowed_keys
        if unknown:
            self.logger.warning(
            f"Unknown keys in global run config ignored: {sorted(unknown)}"
            )
    # -------- Default run_path generator --------
    @staticmethod
    def _default_run_dir(base_path: Path, node_id: str) -> Tuple[Path, int]:
        """
        Erzeugt base_path/runs/{node_id}_run_XXXX mit nächster freier Nummer
        (Run-Zähler ist node-lokal)
        """
        runs_dir = base_path / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        # Regex: exakt dieses Node-Schema matchen
        pattern = re.compile(
            rf"^{re.escape(node_id)}_run_(\d{{4}})$"
        )

        nums = []
        for p in runs_dir.iterdir():
            if not p.is_dir():
                continue
            m = pattern.match(p.name)
            if m:
                nums.append(int(m.group(1)))

        next_run = max(nums) + 1 if nums else 1

        run_path = runs_dir / f"{node_id}_run_{next_run:04d}"
        run_path.mkdir(exist_ok=False)

        return run_path, next_run
