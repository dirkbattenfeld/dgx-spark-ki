#applications/rag_chainlit/test_pipeline-server.py
import json
import asyncio
from ki_dgxsdk.ki_sdk import DGX_Client
from typing import Any, Dict

dgx_client = DGX_Client(use_dispatcher=False)

rag_request_client = dgx_client.get_client("rag_request")

async def ask() -> Dict[str, Any]:
    response = await rag_request_client.call_async(
        endpoint_name="rag_request", 
        prompt="What is known in research about attention in LLMs?",
        system_prompt="Answer only based on the information in your context. If there are no informations available answer: 'No Informations in the context found!'",
        max_tokens=50
    )
    return response

result = asyncio.run(ask())

def print_dict_structure(d: Any, indent: int = 0) -> None:
    """
    Analysiert rekursiv die Struktur eines komplexen Dictionarys/JSONs
    und gibt Typen, Keys und Listen-Längen aus, ohne den Text-Inhalt zu drucken.
    """
    spacing = "  " * indent
    
    if isinstance(d, dict):
        print(f"{spacing}{{ dict mit {len(d)} Keys }}")
        for key, value in d.items():
            # Typ-Bestimmung des Inhalts
            if isinstance(value, dict):
                print(f"{spacing}  {key}:")
                print_dict_structure(value, indent + 2)
            elif isinstance(value, list):
                print(f"{spacing}  {key}: [ list mit {len(value)} Elementen ]")
                if len(value) > 0:
                    # Analysiere das erste Element stellvertretend für die Struktur
                    print(f"{spacing}    ↳ Struktur des ersten Elements:")
                    print_dict_structure(value[0], indent + 3)
            else:
                # Flache Datentypen (str, int, float, bool, None)
                print(f"{spacing}  {key} ({type(value).__name__})")
                
    elif isinstance(d, list):
        print(f"{spacing}[ list mit {len(d)} Elementen ]")
        if len(d) > 0:
            print_dict_structure(d[0], indent + 1)
    else:
        print(f"{spacing}{type(d).__name__}")

filtered_output = {
    "answer": result.get("answer"),
    "generation_info": result.get("generation_info")
}

# 2. Formatiert ins Terminal schreiben
print("\n=== GEFILTERTER PIPELINE OUTPUT ===")
print(json.dumps(filtered_output, indent=2, ensure_ascii=False))


print("\n=== ROHE PIPELINE-ANTWORT ===")
print(json.dumps(result, indent=2, ensure_ascii=False))

print("\n=== ARCHITEKTUR-STRUKTUR DER PIPELINE-ANTWORT ===")
print_dict_structure(result)
