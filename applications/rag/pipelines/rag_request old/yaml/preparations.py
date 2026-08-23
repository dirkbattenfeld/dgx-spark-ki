# --- ADAPTER FÜR DYNAMISCHE OVERRIDES ---

def search_prep(input_data, global_payload):
    # Holt 'limit' aus dem YAML-Job, falls vorhanden
    overrides = {}
    if "limit" in global_payload:
        overrides["limit"] = global_payload["limit"]
    return input_data, overrides

def rerank_prep(input_data, global_payload):
    # Holt 'top_n' aus dem YAML-Job, falls vorhanden
    overrides = {}
    if "top_n" in global_payload:
        overrides["top_n"] = global_payload["top_n"]
    return input_data, overrides

def generate_prep(input_data, global_payload):
    # Holt 'system_prompt' aus dem YAML-Job, falls vorhanden
    overrides = {}
    if "system_prompt" in global_payload:
        overrides["system_prompt"] = global_payload["system_prompt"]
    return input_data, overrides