import yaml
from pathlib import Path

class PromptLoader:
    def __init__(self, base_dir: Path, sys_file: str, req_file: str, context_files: list = None):
        self.base_path = Path(base_dir)
        self.system_prompts = self._load_yaml(self.base_path / sys_file)
        self.requests = self._load_yaml(self.base_path / req_file)
        self.context = self._load_context(context_files) if context_files else ""

    def _load_yaml(self, path: Path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or []

    def _load_context(self, files: list) -> str:
        content = ""
        for f_name in files:
            p = self.base_path / f_name
            if p.exists():
                content += f"\n### DATEI: {f_name}\n" + "="*20 + f"\n{p.read_text(encoding='utf-8')}\n"
        return content

    def get_sys_prompt_by_type(self, p_type: str) -> str:
        return next((sp['system_prompt'] for sp in self.system_prompts if sp['prompt_type'] == p_type), "")

