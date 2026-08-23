# applications/rag_gui/core/redis_bus.py
import asyncio
import json
import logging
import redis.asyncio as aioredis
from typing import Callable, Any, Dict, Awaitable
from rag_gui.core.ports import EventBusPort

logger = logging.getLogger(__name__)

class RedisEventBus(EventBusPort):
    def __init__(self, host: str = "127.0.0.1", port: int = 6379):
        self.redis_url = f"redis://{host}:{port}"
        self._redis_client = None
        self._pubsub = None
        self._listener_task = None
        self._callbacks = {}

    async def connect(self):
        """Baut die asynchrone TCP-Verbindung zu Redis über das Tailscale-Interface auf."""
        if not self._redis_client:
            try:
                self._redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
                self._pubsub = self._redis_client.pubsub()
                # Startet den Hörer-Task im Hintergrund der jeweiligen GUI/Service-Eventloop
                self._listener_task = asyncio.create_task(self._listen_to_redis())
                logger.info(f"📡 Erfolgreich mit Redis Event-Bus verbunden ({self.redis_url})")
            except Exception as e:
                logger.error(f"❌ Fehler beim Verbindungsaufbau zu Redis: {e}")
                raise e

    
    async def publish(self, topic: str, data: Dict[str, Any]) -> None:
        """Feuert ein Event prozessübergreifend in das Tailscale-Netzwerk."""
        if not self._redis_client:
            await self.connect()
        try:
            payload = json.dumps(data)
            await self._redis_client.publish(topic, payload)
        except Exception as e:
            logger.error(f"❌ Fehler beim Veröffentlichen des Events auf {topic}: {e}")

    
    def subscribe(self, pattern: str, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        """Abonniert ein Pattern exakt nach Vorgabe des EventBusPorts."""
        self._callbacks[pattern] = callback

        # Sagt Redis, dass dieser Prozess an dem Pattern interessiert ist (z.B. user:Dirk:*)
        if self._pubsub:
            asyncio.create_task(self._pubsub.psubscribe(pattern))
            logger.info(f"🔍 Pattern erfolgreich abonniert (subscribe): {pattern}")


    async def _listen_to_redis(self):
        """Dauerläufer-Task: Wartet auf eingehende Socket-Nachrichten von Redis,

        sobald Abonnements aktiv sind.
        """
        if not self._pubsub:
            return

        while True:
            try:
                # KORREKTUR: Erst abfragen, wenn wirklich ein Abo existiert!
                # pubsub.patterns enthält die aktiven psubscribe-Registrierungen
                if not self._pubsub.patterns and not self._pubsub.channels:
                    await asyncio.sleep(0.5)
                    continue

                # Polling mit Timeout
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    pattern = message["pattern"]
                    channel = message["channel"]
                    data = json.loads(message["data"])

                    callback = self._callbacks.get(pattern)
                    if callback:
                        await callback(channel, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Verhindert den Spam, falls die Verbindung kurz weg ist
                logger.error(f"⚠️ Fehler im Redis-Listener-Loop: {e}")
                await asyncio.sleep(2)
