"""WebSocket hub for live QA run progress (keyed by run_id)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RunWebSocketManager:
    """Tracks subscribers per run_id and broadcasts JSON event payloads."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._conn_lock = asyncio.Lock()
        self._broadcast_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        async with self._conn_lock:
            self._connections.setdefault(run_id, set()).add(websocket)

    async def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        async with self._conn_lock:
            bucket = self._connections.get(run_id)
            if not bucket:
                return
            bucket.discard(websocket)
            if not bucket:
                del self._connections[run_id]

    async def broadcast(self, run_id: str, payload: dict[str, Any]) -> None:
        """Send one JSON event to all clients listening for this run_id."""
        async with self._broadcast_lock:
            async with self._conn_lock:
                conns = list(self._connections.get(run_id, set()))
            dead: list[WebSocket] = []
            for ws in conns:
                try:
                    await ws.send_json(payload)
                except Exception as e:
                    logger.debug("WebSocket send failed for run %s: %s", run_id, e)
                    dead.append(ws)
            if dead:
                async with self._conn_lock:
                    bucket = self._connections.get(run_id)
                    if bucket:
                        for ws in dead:
                            bucket.discard(ws)
                        if not bucket:
                            del self._connections[run_id]
