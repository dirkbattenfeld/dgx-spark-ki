import ast
import os
import sys
import json
import subprocess
import tempfile

class CodeValidator:
    def __init__(self):
        self.checks = [
            self._check_python_syntax,
            self._check_with_ruff,
            self._check_mandatory_fields
        ]

    def run_all_checks(self, code_content: str) -> list:
        if not code_content:
            return ["FEHLER: Kein Code im Response-Block gefunden."]

        all_errors = []
        for check in self.checks:
            is_ok, error_msg = check(code_content)
            if not is_ok:
                if isinstance(error_msg, list):
                    all_errors.extend(error_msg)
                else:
                    all_errors.append(error_msg)
        return all_errors

    def _check_python_syntax(self, code: str):
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Syntaxfehler Zeile {e.lineno}: {e.msg}"

    def _check_with_ruff(self, code: str):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "ruff", "check", tmp_path, "--select", "E,F", "--output-format", "json"],
                capture_output=True, text=True)
            if result.returncode != 0 and result.stdout:
                data = json.loads(result.stdout)
                return False, [f"RUFF-{e['code']}: {e['message']} (L{e['location']['row']})" for e in data]
            return True, None
        except Exception as e:
            return False, f"Ruff-Fehler: {str(e)}"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _check_mandatory_fields(self, code: str):
        errors = []
        if "INPUT_CLASS =" not in code:
            errors.append("POLICY: 'INPUT_CLASS' fehlt.")
        return (len(errors) == 0, errors)

