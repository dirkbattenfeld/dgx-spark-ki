# peft-0.19.1
# diffusers-0.37.1
# transformers-5.5.4
# accelerate-1.13.0
# huggingface_hub-1.11.0

import os
import logging
import torch
import uvicorn
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
from fastapi import FastAPI
from diffusers import Flux2Pipeline
from pydantic import BaseModel, Field
from PIL import Image

# --- Logging Konfiguration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("gx-diffusers-service")

app = FastAPI(title="Flux.2 Generation Service")

# Verzeichnisse vorbereiten
OUTPUT_DIR = Path("/app/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Modell global laden
hf_token = os.getenv("HF_TOKEN")
model_id = "black-forest-labs/FLUX.2-dev"

logger.info(f"Initialisiere Flux.2 mit bfloat16 auf Blackwell-Architektur...")

try:
    # Laden des Modells
    pipe = Flux2Pipeline.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        token=hf_token
    )
    # Für dein GX10 System mit viel VRAM/Shared Memory:
    pipe.to("cuda")
    logger.info("Flux.2 erfolgreich in den VRAM geladen.")
except Exception as e:
    logger.critical(f"Fehler beim Laden des Modells: {e}")
    raise e

# --- API Modelle ---

class Request(BaseModel):
    # Unterstützt nun einfachen Text oder strukturiertes JSON
    prompt: Union[str, Dict[str, Any]]
    
    # Abwärtskompatible Standardwerte
    height: int = 1024
    width: int = 1024
    guidance_scale: float = 3.5
    num_inference_steps: int = 24
    
    # Neue Flux.2 Features
    reference_images: Optional[List[str]] = Field(default=None, description="Liste absoluter Pfade zu Referenzbildern")
    max_sequence_length: int = 512
    seed: Optional[int] = None

# --- Hilfsfunktionen ---

def load_reference_images(image_paths: List[str]) -> List[Image.Image]:
    """Lädt Bilder von absoluten Pfaden und konvertiert sie für die Pipeline."""
    images = []
    for path_str in image_paths:
        try:
            path = Path(path_str)
            if path.exists():
                # PIL ist format-agnostisch (JPG, PNG, WebP etc. funktionieren)
                img = Image.open(path).convert("RGB")
                images.append(img)
                logger.info(f"Referenzbild geladen: {path_str}")
            else:
                logger.warning(f"Bild nicht gefunden: {path_str}")
        except Exception as e:
            logger.error(f"Fehler beim Laden von {path_str}: {e}")
    return images

# --- Endpunkte ---

@app.post("/generate")
async def generate(request: Request):
    # 1. Prompt-Handling (JSON vs String)
    if isinstance(request.prompt, dict):
        final_prompt = json.dumps(request.prompt)
        logger.info("Verarbeite strukturierten JSON-Prompt.")
    else:
        final_prompt = request.prompt
        logger.info(f"Verarbeite Text-Prompt: {final_prompt[:50]}...")

    # 2. Seed-Handling
    generator = None
    if request.seed is not None:
        generator = torch.Generator("cuda").manual_seed(request.seed)

    # 3. Vorbereitung der Argumente
    generation_kwargs = {
        "prompt": final_prompt,
        "height": request.height,
        "width": request.width,
        "guidance_scale": request.guidance_scale,
        "num_inference_steps": request.num_inference_steps,
        "max_sequence_length": request.max_sequence_length,
        "generator": generator
    }

    # 4. Laden der Referenzbilder (Flux.2 Feature)
    if request.reference_images:
        ref_imgs = load_reference_images(request.reference_images)
        if ref_imgs:
            # Das Argument für Multi-Reference in der Flux2-Pipeline
            generation_kwargs["image"] = ref_imgs

    start_time = datetime.now()

    try:
        # Generierung
        result = pipe(**generation_kwargs)
        image = result.images[0]

        # Speichern
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_image.png"
        full_path = OUTPUT_DIR / filename
        image.save(full_path)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Generierung abgeschlossen in {duration:.2f}s")

        return {
            "status": "success",
            "image_path": str(full_path),
            "filename": filename,
            "metadata": {
                "duration_seconds": duration,
                "model": model_id,
                "seed": request.seed,
                "parameters": {
                    "steps": request.num_inference_steps,
                    "guidance": request.guidance_scale,
                    "max_sequence": request.max_sequence_length
                }
            }
        }

    except Exception as e:
        logger.error(f"Fehler bei der Generierung: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/models")
async def get_models():
    return {"active_model": model_id, "supported_features": ["multi-reference", "json-prompting", "nvfp4-compatible"]}

#if __name__ == "__main__":
#    # Port 8889 wie in deinem Ursprungs-Setup
#    uvicorn.run(app, host="0.0.0.0", port=8889)
    