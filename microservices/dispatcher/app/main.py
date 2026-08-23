import os
import uvicorn
import sys
import asyncio
import logging
import logging.handlers
import traceback
import time
import uuid
import yaml  
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import httpx

# ==========================================
# LOGGING (CONSOLE & FILE)
# ==========================================
log_format = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-18s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)

# File Handler (Rotierend, um die SSD zu schonen)
file_handler = logging.handlers.RotatingFileHandler(
    "dispatcher.log", 
    maxBytes=10*1024*1024, # 10 MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(log_format)

# Root Logger Setup
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger("Dispatcher-Main")

# ==========================================
# GLOBALE VARIABLEN & SDK
# ==========================================
TIMEOUT = 600
BATCH_TIMEOUT = 0.05

# Performance- und Zustandsmetriken für das TUI-Dashboard
START_TIME = time.time()
STATS = {
    "total_received": 0,
    "total_completed": 0,
    "total_failed": 0
}
ACTIVE_QUEUES = {}
MATRIX_STATS = {}

# Helper für das Matrix-Tracking (Verhindert KeyErrors und hält Code sauber)
def increment_matrix(service_id: str, queue_id: str):
    if service_id not in MATRIX_STATS:
        MATRIX_STATS[service_id] = {}
    if queue_id not in MATRIX_STATS[service_id]:
        MATRIX_STATS[service_id][queue_id] = 0
    MATRIX_STATS[service_id][queue_id] += 1

def decrement_matrix(service_id: str, queue_id: str):
    if service_id in MATRIX_STATS and queue_id in MATRIX_STATS[service_id]:
        if MATRIX_STATS[service_id][queue_id] > 0:
            MATRIX_STATS[service_id][queue_id] -= 1
            

# ==========================================
# KLASSEN & MODELLE
# ==========================================

class DispatcherJob(BaseModel):
    service_id: str
    endpoint: str
    queue_id: str
    batching: bool
    max_batch_size: int
    payload: Dict[str, Any]

class ms_dgx_job(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "pending"
    created_at: float = Field(default_factory=time.time)
    job_def: DispatcherJob

class OpenAIPrompt(BaseModel):
    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    stream: Optional[bool] = False

    
# ==========================================
# DASHBOARD TUI SERVER
# ==========================================
async def handle_tui_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    client_addr = writer.get_extra_info('peername')
    logger.info(f"📊 TUI-Monitoring Client verbunden: {client_addr}")
    
    try:
        while True:
            uptime = int(time.time() - START_TIME)
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            output = "\033[H\033[2J"
            output += "=============================================================================================================================\n"
            output += f"DGX SPARK DISPATCHER LIVE MATRIX | Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            output += "=============================================================================================================================\n"
            output += f"Jobs: {STATS['total_received']} Received | {STATS['total_completed']} Done | {STATS['total_failed']} Fail\n"
            output += "-----------------------------------------------------------------------------------------------------------------------------\n\n"
            
            # 1. Spalten (Lanes) und Zeilen (Services) bestimmen
            lanes = sorted(list(ACTIVE_QUEUES.keys()))
            services = sorted(list(MATRIX_STATS.keys()))
            
            if not lanes:
                output += "Warte auf Initialisierung der Lanes...\n"
            else:
                # Spaltenbreiten definieren
                svc_width = 20
                col_width = 15
                
                # --- HEADER ZEILE ---
                header = f"{'MICROSERVICE':<{svc_width}} | "
                for lane in lanes:
                    header += f"{lane.upper():<{col_width}}"
                header += f"| {'TOTAL':<{col_width}}\n"
                output += header
                output += "-" * len(header) + "\n"
                
                # --- ZEILEN (SERVICES) + INHALT ---
                lane_totals = {lane: 0 for lane in lanes}
                grand_total = 0
                
                for svc in services:
                    row_total = 0
                    row_str = f"{svc:<{svc_width}} | "
                    
                    for lane in lanes:
                        # Hole den aktuellen Zählerstand aus der Matrix
                        count = MATRIX_STATS.get(svc, {}).get(lane, 0)
                        row_total += count
                        lane_totals[lane] += count
                        
                        # Wenn 0, machen wir es übersichtlicher mit einem Punkt, sonst die Zahl
                        val_str = str(count) if count > 0 else "."
                        row_str += f"{val_str:<{col_width}}"
                        
                    grand_total += row_total
                    row_str += f"| \033[1m{row_total:<{col_width}}\033[0m\n"
                    output += row_str
                    
                # --- FOOTER ZEILE (SPALTENSUMMEN) ---
                output += "-" * len(header) + "\n"
                footer_str = f"\033[1m{'TOTAL':<{svc_width}}\033[0m | "
                for lane in lanes:
                    footer_str += f"\033[1m{lane_totals[lane]:<{col_width}}\033[0m"
                footer_str += f"| \033[1m{grand_total:<{col_width}}\033[0m\n"
                output += footer_str
                
            output += "=============================================================================================================================\n"
            
            writer.write(output.encode('utf-8'))
            await writer.drain()
            await asyncio.sleep(0.5)  # Auf 0.5s verkürzt für knackigere Live-Updates
            
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        logger.info(f"🔌 TUI-Monitoring Client getrennt: {client_addr}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ==========================================
# LIFESPAN & QUEUE-SETUP
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starte Dispatcher: Lade microservices.yaml.")

    config_path = os.environ.get("MICROSERVICE_CONFIG_PATH", "/app/microservices.yaml")
    logger.info(f"📂 Lade Konfiguration aus: {config_path}")

    # Konfiguration microservices.yaml laden    
    try:
        with open(config_path, "r") as f:
            app.state.config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"❌ Konnte microservices.yaml nicht lesen: {e}")
        app.state.config = {"services":{}}
    
    services = app.state.config.get("services", {})
    unique_queues = set(s.get("queue_id", "standard") for s in services.values())
    unique_queues.add("standard")
    
    # Globaler HTTP Client mit Connection-Pooling initialisiert
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=TIMEOUT)
    
    app.state.queues = {}
    worker_tasks = []
    # Worker Lanes initialisieren
    for qid in unique_queues:
        app.state.queues[qid] = asyncio.Queue()
        task = asyncio.create_task(generic_worker(qid, app.state.queues[qid], app))
        worker_tasks.append(task)
        logger.info(f"🛣️ Lane '{qid}' geöffnet und Worker gestartet.")

    # TUI-Server auf Port 9999 für netcat starten (Lauscht auf allen Schnittstellen für z.B. Tailscale)
    global ACTIVE_QUEUES
    ACTIVE_QUEUES = app.state.queues

    tui_task = None
    try:
        tui_server = await asyncio.start_server(handle_tui_client, '0.0.0.0', 9999)
        tui_task = asyncio.create_task(tui_server.serve_forever())
        logger.info("📊 TUI-Dashboard-Server lauscht auf Port 9999 (Abo via 'nc localhost 9999')")
    except Exception as e:
        logger.error(f"❌ Konnte TUI-Server nicht starten: {e}")
        
    yield
    
    # ==========================
    # CLEAN SHUTDOWN 
    # ==========================
    logger.info("🛑 Beende Dispatcher: Bereinige Ressourcen...")
    
    if tui_task:
        tui_task.cancel()
        # Auf das Ende des TUI-Servers warten, um Task-Lecks zu verhindern
        await asyncio.gather(tui_task, return_exceptions=True)

    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    
    # Connection Pool sauber schließen
    await app.state.http_client.aclose()
    logger.info("✅ Dispatcher heruntergefahren.")

app = FastAPI(
    title="Microservice-Dispatcher",
    lifespan=lifespan
)


# ==========================================
# ENDPUNKTE
# ==========================================
@app.get("/health")
async def health_check(request: Request):
    """
    Health-Check für Docker / Orchestrierung.
    """
    app_queues = request.app.state.queues
    return {
        "status": "online",
        "message": "Microservice-Dispatcher ist bereit.",
        "queues_snapshot": {qid: q.qsize() for qid, q in app_queues.items()},
        "stats": STATS
    }


@app.get("/routes")
async def get_routes(request: Request):
    return request.app.state.config


@app.post("/submit")
async def submit_job(job: DispatcherJob, request: Request):
    req_logger = logging.getLogger("API-Submit")
    STATS["total_received"] += 1
    
    if isinstance(job.payload, dict) and job.payload.get("stream", False):
        STATS["total_failed"] += 1
        req_logger.warning(f"🛑 Abgewiesen: Streaming-Job über /submit versucht (Service: {job.service_id}).")
        raise HTTPException(
            status_code=400, 
            detail="Streaming is not supported on the /submit endpoint. Please use the OpenAI-compatible endpoint (/v1/chat/completions) for streaming."
        )
    
    app_queues = request.app.state.queues
    if job.queue_id in app_queues:
        target_queue = app_queues[job.queue_id]
        actual_queue_id = job.queue_id
    else:
        req_logger.warning(f"Unbekannte Queue '{job.queue_id}', nutze 'standard'")
        target_queue = app_queues.get("standard")
        actual_queue_id = "standard"
        job.queue_id = "standard"
    
    increment_matrix(job.service_id, actual_queue_id)
    
    tracking_job = ms_dgx_job(job_def=job)
    ticket = asyncio.get_running_loop().create_future()

    await target_queue.put({"tracking": tracking_job, "ticket": ticket, "stream_bridge": None})
    req_logger.info(f"📥 Job {tracking_job.job_id} ({job.service_id}/{job.endpoint}) in Lane '{job.queue_id}' eingereiht.")

    try:
        result = await asyncio.wait_for(ticket, timeout=TIMEOUT)
        STATS["total_completed"] += 1
        return result
    except asyncio.TimeoutError:
        STATS["total_failed"] += 1
        req_logger.error(f"⏱️ Timeout für Job {tracking_job.job_id}")
        raise HTTPException(status_code=504, detail="Timeout in der Pipeline.")
    except Exception as e:
        STATS["total_failed"] += 1
        req_logger.error(f"❌ Fehler bei Job {tracking_job.job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def openai_chat_endpoint(prompt: OpenAIPrompt, request: Request):
    req_logger = logging.getLogger("API-OpenAI")
    STATS["total_received"] += 1
    
    config = request.app.state.config
    app_queues = request.app.state.queues
    
    vllm_config = config.get("services", {}).get("vllm", {})
    target_queue_id = vllm_config.get("queue_id", "standard")
    target_endpoint = vllm_config.get("endpoint", "v1/chat/completions")    
    
    req_logger.info(f"🤖 OpenAI Request empfangen (Stream={prompt.stream}). Route an Queue '{target_queue_id}'.")

    job = DispatcherJob(
        service_id="vllm", 
        endpoint=target_endpoint, 
        queue_id=target_queue_id,
        batching=False, 
        max_batch_size=1,
        payload=prompt.model_dump()
    )

    increment_matrix("vllm", target_queue_id)

    tracking_job = ms_dgx_job(job_def=job)
    ticket = asyncio.get_running_loop().create_future()
    
    # Wenn Streaming aktiv ist, bauen wir eine asynchrone Brücken-Queue für die Chunks
    stream_bridge = asyncio.Queue() if prompt.stream else None

    target_queue = app_queues.get(target_queue_id, app_queues.get("standard"))
    
    if target_queue is None:
        STATS["total_failed"] += 1
        decrement_matrix("vllm", target_queue_id)
        raise HTTPException(status_code=500, detail="Warteschlange nicht verfügbar.")
    
    await target_queue.put({
        "tracking": tracking_job, 
        "ticket": ticket, 
        "stream_bridge": stream_bridge
    })

    try:
        if prompt.stream:
            # Der Endpunkt wartet nicht auf das Ticket, sondern gibt sofort eine 
            # StreamingResponse zurück, die live aus der stream_bridge liest.
            async def chunk_generator():
                try:
                    while True:
                        chunk = await stream_bridge.get()
                        if chunk is None:  # Stop-Signal vom Worker
                            break
                        if isinstance(chunk, Exception): # Fehler-Signal vom Worker
                            yield f"data: {{\"error\": \"Stream interrupted: {str(chunk)}\"}}\n\n"
                            break
                        yield chunk
                    STATS["total_completed"] += 1
                except Exception:
                    STATS["total_failed"] += 1
                    yield f"data: {{\"error\": \"Stream internal error\"}}\n\n"
                    
            return StreamingResponse(chunk_generator(), media_type="text/event-stream")
        else:
            # Normaler Request (JSON): Warte auf das fertige Ergebnis im Ticket
            result = await asyncio.wait_for(ticket, timeout=TIMEOUT)
            STATS["total_completed"] += 1
            return result

    except asyncio.TimeoutError:
        STATS["total_failed"] += 1
        raise HTTPException(status_code=504, detail="Timeout beim Warten auf vLLM.")
    except Exception as e:
        STATS["total_failed"] += 1
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# WORKER LOGIK 
# ==========================================

async def generic_worker(queue_id: str, queue: asyncio.Queue, app: FastAPI):
    w_log = logging.getLogger(f"Worker-[{queue_id}]")
    
    # Lokaler Zwischenpuffer für entnommene aber nicht zum Batch passende Jobs
    local_buffer = []
    
    while True:
        try:
            if local_buffer:
                first_item = local_buffer.pop(0)
            else:
                first_item = await queue.get()
                
            tracking: ms_dgx_job = first_item["tracking"]
            job_def: DispatcherJob = tracking.job_def
            batch = [first_item]

            if job_def.batching and job_def.max_batch_size > 1:
                start_time = asyncio.get_event_loop().time()
                while len(batch) < job_def.max_batch_size:
                    time_left = BATCH_TIMEOUT - (asyncio.get_event_loop().time() - start_time)
                    if time_left <= 0:
                        break
                    
                    try:
                        # Zuerst den lokalen Puffer leeren
                        if local_buffer:
                            next_item = local_buffer.pop(0)
                        else:
                            next_item = await asyncio.wait_for(queue.get(), timeout=time_left)

                        next_tracking: ms_dgx_job = next_item["tracking"]
                        next_job: DispatcherJob = next_tracking.job_def

                        # Streaming-Jobs dürfen NICHT gebatched werden (wichtig für die Brücke!)
                        if next_item["stream_bridge"] is not None or first_item["stream_bridge"] is not None:
                            local_buffer.append(next_item)
                            break

                        if next_job.service_id == job_def.service_id and next_job.endpoint == job_def.endpoint:
                            batch.append(next_item)
                        else:
                            local_buffer.append(next_item)
                            break
                    except asyncio.TimeoutError:
                        break

            w_log.info(f"⚙️ Führe Batch aus: {job_def.service_id} | Size: {len(batch)}")
            
            coroutines = [execute_single(item, app) for item in batch]
            await asyncio.gather(*coroutines)
            
            for _ in batch:
                try:
                    queue.task_done()
                except ValueError:
                    pass
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            w_log.error(f"💥 Kritischer Fehler im Worker: {traceback.format_exc()}")


async def execute_single(queue_item: dict, app: FastAPI):
    tracking: ms_dgx_job = queue_item["tracking"]
    job_def: DispatcherJob = tracking.job_def
    ticket: asyncio.Future = queue_item["ticket"]
    stream_bridge: Optional[asyncio.Queue] = queue_item["stream_bridge"]
    e_log = logging.getLogger("Worker-Execute")

    try:
        http_client: httpx.AsyncClient = app.state.http_client
        service_cfg = app.state.config.get("services", {}).get(job_def.service_id, {})
        host = service_cfg.get("host", "localhost")
        port = service_cfg.get("port", 8000)
        url = f"http://{host}:{port}/{job_def.endpoint}"
        
        # Wenn eine stream_bridge existiert, konsumiert der Worker den Stream live
        if stream_bridge is not None:
            e_log.info(f"🌊 Starte Stream-Auslesung für Job {tracking.job_id}")
            
            async with http_client.stream("POST", url, json=job_def.payload) as response:
                if response.status_code != 200:
                    raise Exception(f"HTTP Stream Error ({response.status_code})")
                
                async for line in response.aiter_lines():
                    if line:
                        # Schiebe jede empfangene SSE-Zeile direkt in die Brücke
                        await stream_bridge.put(f"{line}\n\n")
                        
            # Signalisiere dem Endpunkt das Ende des Streams
            await stream_bridge.put(None)
            tracking.status = "completed"
            
            # Das Ticket kriegt nur ein True, da die Daten schon über die Brücke geflossen sind
            if not ticket.done():
                ticket.set_result(True)
        else:
            # Normaler Nicht-Streaming-Ablauf
            response = await http_client.post(url, json=job_def.payload)
            if response.status_code != 200:
                raise Exception(f"HTTP Error ({response.status_code}): {response.text}")
            
            tracking.status = "completed"
            if not ticket.done():
                ticket.set_result(response.json())
                
    except Exception as e:
        tracking.status = "failed"
        e_log.error(f"❌ Ausführungsfehler bei Job {tracking.job_id}: {e}")
        
        if stream_bridge is not None:
            # Schicke den Fehler an die Brücke, damit der Client bescheid weiß
            await stream_bridge.put(e)
        if not ticket.done():
            ticket.set_exception(e)

    finally:
        decrement_matrix(job_def.service_id, job_def.queue_id)

