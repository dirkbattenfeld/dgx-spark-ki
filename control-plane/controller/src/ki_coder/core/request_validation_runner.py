import datetime
from pathlib import Path
from typing import Dict, Any, List

from ki_coder.core.runner import InferenceRunner
from ki_coder.core.prompt_factory import PromptBuilder
from ki_coder.data.loader import PromptLoader
from ki_coder.data.logger import ResultLogger
from ki_coder.validation.validator import CodeValidator
from ki_coder.validation.extractor import extract_code_from_markdown

class Request_Validation_Runner:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den Orchestrator mit einem Konfigurations-Dictionary.
        """
        self.base_dir = Path(config["base_dir"])
        self.input_dir = self.base_dir / config["input_dir"]
        self.output_dir = self.base_dir / config["output_dir"]
        self.output_file_suffix = config["output_file_suffix"]
        self.iterations = config.get("iterations", 3)
        self.model_settings = config["model_settings"]
        
        # Initialisierung der Core-Komponenten
        self.loader = PromptLoader(
            self.input_dir, 
            config["system_prompts_file"], 
            config["requests_file"]
        )
        self.runner = InferenceRunner(self.model_settings)
        self.validator = CodeValidator()
        self.builder = PromptBuilder(
            revision_system_prompt=config.get("revision_system_prompt", "")
        )
        
        # Filter-Parameter
        self.allowed_prompt_types = config.get("allowed_prompt_types", [])
        self.max_requests = config.get("max_requests", float('inf'))

    def _prepare_batch(self) -> List[Dict[str, Any]]:
        """Filtert die Requests basierend auf Typ und Anzahl."""
        filtered_requests = []
        
        for req in self.loader.requests:
            # Filter 1: Prompt Type
            if self.allowed_prompt_types and req.get("prompt_type") not in self.allowed_prompt_types:
                continue
            
            filtered_requests.append({
                **req, 
                "validation_errors": None, 
                "response": None
            })
            
            # Filter 2: Max Requests
            if len(filtered_requests) >= self.max_requests:
                break
                
        return filtered_requests

    def run(self):
        """Startet den Iterations-Prozess."""
        current_batch = self._prepare_batch()
        
        if not current_batch:
            print("[-] Kein Batch zum Verarbeiten gefunden (Filter prüfen).")
            return

        for i in range(self.iterations + 1):
            prefix = f"{i:02d}"
            run_id = f"{prefix}_{self.output_file_suffix}"
            logger = ResultLogger(run_id, self.output_dir)
            logger.write_meta_log(self.model_settings, {"iteration": i})

            print(f"\n--- LAUF {prefix} START (Batch Größe: {len(current_batch)}) ---")
            next_batch = []
            any_errors_left = False

            for req in current_batch:
                # Skip wenn bereits valide
                if req.get("validation_errors") == [] and i > 0:
                    next_batch.append(req)
                    continue

                print(f"[*] Verarbeite Request {req['id']} ({req['prompt_type']})...")

                # 1. Prompt Bauen
                base_sys = self.loader.get_sys_prompt_by_type(req['prompt_type'])
                sys_p, user_p = self.builder.build(req, base_sys, self.loader.context)

                # 2. Inferenz
                result = self.runner.run(sys_p, user_p)

                # 3. Code extrahieren & Validieren
                code = extract_code_from_markdown(result['response'])
                errors = self.validator.run_all_checks(code)

                if errors:
                    any_errors_left = True
                    print(f"    [!] {len(errors)} Fehler gefunden.")
                else:
                    print(f"    [OK] Code ist valide.")

                # 4. Record aktualisieren
                updated_record = {
                    **req,
                    "response": result['response'],
                    "validation_errors": errors,
                    "metrics": result['metrics'],
                    "iteration": i,
                    "timestamp": datetime.datetime.now().isoformat()
                }

                logger.append_result(updated_record)
                next_batch.append(updated_record)

            current_batch = next_batch

            if not any_errors_left:
                print(f"\n✅ ERFOLG: Alle Codes in Iteration {prefix} sind fehlerfrei.")
                break

            if i == self.iterations:
                print(f"\n⚠️ LIMIT: Maximale Iterationen ({self.iterations}) erreicht.")