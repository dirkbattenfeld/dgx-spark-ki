import re

def extract_code_from_markdown(text: str) -> str:
    """Extrahiert den Inhalt aus ```python ... ``` Blöcken."""
    if not text:
        return ""
    pattern = r"```python\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: Falls der LLM die Ticks vergisst, aber Python-Code sendet
    return text.strip()

