import json
import datetime
from pathlib import Path

class ResultLogger:
    def __init__(self, run_id: str, base_dir: str):
        self.base_path = Path(base_dir)
        self.jsonl_path = self.base_path / f"{run_id}.jsonl"
        self.log_path = self.base_path / f"{run_id}.log"

    def write_meta_log(self, config: dict, context_info: dict):
        meta = {
            "timestamp": datetime.datetime.now().isoformat(),
            "config": config,
            "context": context_info
        }
        self.log_path.write_text(json.dumps(meta, indent=4), encoding='utf-8')

    def append_result(self, entry: dict):
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
