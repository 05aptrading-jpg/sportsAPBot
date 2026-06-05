import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.connections.add(ws)
        logger.info(f"WebSocket conectado: {len(self.connections)} total")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.connections.discard(ws)
        logger.info(f"WebSocket desconectado: {len(self.connections)} restantes")

    async def broadcast(self, data: dict):
        msg = json.dumps(data, ensure_ascii=False, default=str)
        stale = set()
        async with self._lock:
            for ws in self.connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    stale.add(ws)
            self.connections -= stale
