import asyncio
import json
import logging
from typing import Any, Dict, Optional
import redis.asyncio as aioredis

from libs.streampipe.factory import PipelineRunnerFactory
from libs.streampipe.basemodels import BasePipelineEnv

logger = logging.getLogger(__name__)


class PipelineEventWorker:
    """
    Asynchroner Event-Worker:
    1. Liest Job-Events aus Redis Stream (Consumer Group).
    2. Hydriert den Payload aus PostgreSQL / S3.
    3. Führt die Pipeline via StreamPipe Runner aus.
    4. Sendet Live-Progress Events an Redis.
    5. Persistiert Resultate in Postgres & Garage S3.
    """
    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        env: BasePipelineEnv,
        pipeline_registry: Dict[str, Any],
        db_client: Any,      # PostgreSQL Client / Service
        s3_client: Any       # Garage S3 Client
    ):
        self.redis = redis_client
        self.stream_key = stream_key
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.env = env
        self.registry = pipeline_registry
        self.db = db_client
        self.s3 = s3_client

    async def init_consumer_group(self):
        """Erstellt die Redis Consumer Group, falls sie noch nicht existiert."""
        try:
            await self.redis.xgroup_create(
                name=self.stream_key, 
                groupname=self.group_name, 
                id="0", 
                mkstream=True
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def emit_progress(self, job_id: str, step_name: str, status: str, details: Optional[Dict[str, Any]] = None):
        """Sendet Fortschritts-Events an einen Redis Stream oder Pub/Sub Kanal."""
        event_data = {
            "job_id": job_id,
            "step": step_name,
            "status": status,
            "details": details or {}
        }
        # Publish an Pub/Sub für Live-UI oder Ingest-Stream
        await self.redis.publish(f"pipeline:events:{job_id}", json.dumps(event_data))

    async def process_job(self, message_id: str, job_data: Dict[str, Any]):
        job_id = job_data["job_id"]
        pipeline_id = job_data["pipeline_id"]
        mode = job_data.get("mode", "single")
        payload_ref = job_data["payload_ref"]
        overrides = job_data.get("overrides")

        logger.info("⚡ [Worker] Starte Job %s (Pipeline: %s, Mode: %s)", job_id, pipeline_id, mode)
        await self.emit_progress(job_id, "SYSTEM", "STARTED")

        # 1. Pipeline-Definition laden
        pipeline_def = self.registry.get(pipeline_id)
        if not pipeline_def:
            logger.error("Pipeline '%s' nicht gefunden.", pipeline_id)
            await self.emit_progress(job_id, "SYSTEM", "FAILED", {"error": "Pipeline not found"})
            await self.redis.xack(self.stream_key, self.group_name, message_id)
            return

        steps = pipeline_def["steps"]
        initial_input_class = pipeline_def["initial_input_class"]

        # 2. Payload-Hydrierung aus PostgreSQL
        try:
            initial_payload = await self.db.get_payload_by_ref(payload_ref)
        except Exception as e:
            logger.error("Fehler beim Laden des Payloads aus Postgres: %s", e)
            await self.emit_progress(job_id, "SYSTEM", "FAILED", {"error": f"DB Fetch Error: {str(e)}"})
            await self.redis.xack(self.stream_key, self.group_name, message_id)
            return

        # 3. Runner instanziieren
        runner = PipelineRunnerFactory.create(
            mode=mode,
            steps=steps,
            env=self.env,
            initial_input_class=initial_input_class
        )

        # 4. Pipeline-Ausführung
        try:
            results = await runner.run(
                initial_payload=initial_payload,
                overrides=overrides
            )

            # 5. Resultate speichern: Artefakte/Schwere Daten -> S3, Status & Metadaten -> Postgres
            s3_path = f"artifacts/{job_id}/results.json"
            await self.s3.write_json(s3_path, results)
            
            await self.db.update_job_status(
                job_id=job_id, 
                status="COMPLETED", 
                result_s3_ref=s3_path
            )

            await self.emit_progress(job_id, "SYSTEM", "COMPLETED", {"s3_ref": s3_path})
            
            # Message Acknowledgement in Redis
            await self.redis.xack(self.stream_key, self.group_name, message_id)

        except Exception as e:
            logger.error("Kritischer Fehler bei Ausführung von Job %s: %s", job_id, e, exc_info=True)
            await self.db.update_job_status(job_id=job_id, status="FAILED", error=str(e))
            await self.emit_progress(job_id, "SYSTEM", "FAILED", {"error": str(e)})
            await self.redis.xack(self.stream_key, self.group_name, message_id)

    async def start_listening(self):
        """Hauptschleife des Workers."""
        await self.init_consumer_group()
        logger.info("👂 Event-Worker '%s' lauscht auf Stream '%s'...", self.consumer_name, self.stream_key)

        while True:
            try:
                # Lesen von ungelesenen Nachrichten aus der Consumer Group
                entries = await self.redis.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=1,
                    block=2000  # 2 Sekunden Blockzeit
                )

                if not entries:
                    continue

                for _, messages in entries:
                    for message_id, raw_data in messages:
                        # Raw Redis Payload parsen
                        job_data = json.loads(raw_data[b"data"].decode("utf-8"))
                        await self.process_job(message_id.decode("utf-8"), job_data)

            except asyncio.CancelledError:
                logger.info("Worker-Loop beendet.")
                break
            except Exception as e:
                logger.error("Fehler im Worker-Loop: %s", e, exc_info=True)
                await asyncio.sleep(1)

