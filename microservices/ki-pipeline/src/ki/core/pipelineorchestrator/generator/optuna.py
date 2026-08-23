# ki/core/pipelineorchestrator/optuna.py
from ki.core.pipelineorchestrator.generator.registry import generator_registry
from ki.core.pipelineorchestrator.generator.base import BaseRunGenerator

import logging
import optuna
from typing import Dict, Any, Generator
from abc import ABC, abstractmethod

RunOverrides = Dict[str, Dict[str, Any]]

import os 
optuna_db_url = os.environ["OPTUNA_DB_URL"] 

@generator_registry.register("optuna")
class RunGeneratorOptuna(BaseRunGenerator):
    """
    Generator für Hyperparameter-Optimierung mit Optuna.
    Liefert Overrides iterativ, bekommt die Metrik zurück,
    meldet diese an Optuna, fordert den nächsten Trial.
    """
    ExpectsFeedback: bool = True
    
    def __init__(self, logger:logging.logger, **kwargs):
        self.logger = logger
        # Optuna-Basisparameter
        self.study_name: str = kwargs.get("study_name")
        self.sampler_type: str = kwargs.get("sampler_type", "TPE")
        self.direction: str = kwargs.get("direction", "maximize")
        self.metric: str = kwargs.get("metric")
        self.pruner_type: Optional[str] = kwargs.get("pruner_type")
        self.n_trials: Optional[int] = kwargs.get("n_trials", 10)
        self.target_component: str = kwargs.get("target_component")
        self.parameter_prefix: str = kwargs.get("parameter_prefix", None)
        self.search_space: Optional[dict] = kwargs.get("search_space", {})

        # Study erstellen
        self.storage = optuna_db_url
        sampler = self._get_sampler(self.sampler_type)
        self.logger.info(f"Initialisiere Optuna Study '{self.study_name}'")
        self._study = optuna.create_study(
            study_name=self.study_name,
            direction=self.direction,
            sampler=sampler,
            storage=self.storage,
            load_if_exists=True
        )
        
    def _get_sampler(self, s_type: str):
        if s_type.upper() == "TPE": return optuna.samplers.TPESampler()
        if s_type.upper() == "RANDOM": return optuna.samplers.RandomSampler()
        raise ValueError(f"Sampler '{s_type}' nicht unterstützt.")

    @classmethod
    def from_config(cls, config: Dict[str, Any], logger: logging.logger) -> "RunGeneratorOptuna":
        # Extrahiert optuna_base und search_space sauber
        base_params = config.get("optuna_base", {})
        s_space = config.get("search_space", {})
        return cls(logger=logger, **(base_params | {"search_space": s_space}))

    def process_feedback(self, result: Any) -> float:
        """Wird vom Orchestrator aufgerufen."""
        metric_value = self._extract_metric(result, self.metric)
        
        if metric_value is not None:
            logger.info(f"[Optuna Feedback]: {self.metric} = {metric_value}")
        else:
            logger.warning(f"[Optuna] Metrik '{self.metric}' konnte im Resultat nicht gefunden werden!")
            
        return metric_value

    def _extract_metric(self, pipeline_result, metric_name: str) -> Optional[float]:
        """Interne Hilfsmethode zum Crawlen des Result-Objekts."""
        try:
            for comp_result in pipeline_result.component_results:
                metrics = comp_result.outputs_summary.get("results")
                if metrics and metric_name in metrics:
                    return float(metrics[metric_name])
        except Exception as e:
            logger.error(f"Fehler bei Metrik-Extraktion: {e}")
        return None
    

    def generate(self) -> Generator[Dict[str, Any], float, None]:
        """
        Iterable Generator:
        - yield Overrides pro Trial
        - Orchestrator extrahiert metric aus pipelineresults mit Methode des Generators
        - und sendet die Metrik zurück an den Generator
        - Metrik wird an Optuna gemeldet
        """
        trials_done = 0
        while trials_done < self.n_trials:
            trial = self._study.ask()  # neuer Trial

            # Overrides aus Search Space generieren
            target_component_overrides = {}

            for param_name, param_def in self.search_space.items():
                method_name = param_def["method"]
                args = param_def.get("args", [])
                kwargs = param_def.get("kwargs", {})
                method = getattr(trial, method_name)
                target_component_overrides[param_name] = method(param_name, *args, **kwargs)

            if self.parameter_prefix:
                # merge eine Ebene tiefer, bspw. bei ml_runner
                overrides = {self.target_component: {self.parameter_prefix: target_component_overrides}}
            else:
                # merge direkt in die config der Komponente
                overrides = {self.target_component: target_component_overrides}

            # --- YIELD & SEND ---
            # Der Generator pausiert hier und wartet auf das Ergebnis von .send()
            metric = yield overrides
            
            # Rückmeldung an Optuna
            if metric is not None:
                self._study.tell(trial, metric)
                logger.info(f"[Optuna] Trial {trial.number} abgeschlossen mit {self.metric}: {metric}")
            else:
                # Falls keine Metrik kam, Trial als Fail markieren (optional)
                self._study.tell(trial, state=optuna.trial.TrialState.FAIL)

            trials_done += 1
