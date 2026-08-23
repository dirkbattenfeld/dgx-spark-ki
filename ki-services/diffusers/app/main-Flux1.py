import os
import logging
import torch
import uvicorn
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from diffusers import FluxPipeline
from pydantic import BaseModel

# --- Logging Konfiguration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("gx diffusers service")

# App Instanz erstellen
app = FastAPI()

# Verzeichnisse vorbereiten
OUTPUT_DIR = Path("/app/outputs")
try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Ausgabeverzeichnis bereit: {OUTPUT_DIR}")
except Exception as e:
    logger.error(f"Fehler beim Erstellen des Verzeichnisses: {e}")

# Modell global laden (beim Start des Containers)
hf_token = os.getenv("HF_TOKEN")
model_id = "black-forest-labs/FLUX.1-dev"

logger.info(f"Starte Ladevorgang für Modell: {model_id}")

try:
    # Das Laden kann dauern, daher loggen wir davor und danach
    pipe = FluxPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        token=hf_token
    )
    pipe.to("cuda")
    logger.info("Modell erfolgreich in den VRAM geladen und auf CUDA verschoben.")
except Exception as e:
    logger.critical(f"Kritischer Fehler beim Laden des Modells: {e}")
    raise e

# Definiere, wie die Anfrage aussehen muss
class Request(BaseModel):
    prompt: str

@app.post("/generate")
async def generate(request: Request):
    logger.info(f"Generierungsanfrage empfangen. Prompt: '{request.prompt}'")

    start_time = datetime.now()

    try:
        # Generierung
        image = pipe(
            request.prompt,
            height=1024,
            width=1024,
            guidance_scale=3.5,
            num_inference_steps=24,
            max_sequence_length=512
        ).images[0]

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_image.png"
        full_path = OUTPUT_DIR / filename

        image.save(full_path)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Bild erfolgreich generiert und gespeichert: {filename} (Dauer: {duration:.2f}s)")

        return {
            "status": "success",
            "image_path": str(full_path),
            "filename": filename,
            "duration_seconds": duration
        }

    except Exception as e:
        logger.error(f"Fehler während der Bildgenerierung für Prompt '{request.prompt}': {e}")
        return {"status": "error", "message": str(e)}

@app.get("/models")
async def models():
    logger.info("Modell-Liste angefragt")
    return [model_id]

#Server Start
#if __name__ == "__main__":
#    uvicorn.run(app, host="0.0.0.0", port=8889)
