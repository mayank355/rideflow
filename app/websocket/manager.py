from fastapi import WebSocket
from typing import Dict


class ConnectionManager:
    """
    In-memory registry mapping an id (driver_id or rider_id) to their
    currently open WebSocket connection.

    Deliberately NOT persisted anywhere (no Postgres, no Redis) — this is
    correct, not an oversight. If the server restarts, every connection
    drops anyway (the underlying TCP socket is gone), so there is nothing
    meaningful to "recover." The client simply reconnects, and a fresh
    entry gets written here. Same self-healing property as driver
    locations in Redis: only the current value matters, never the history.

    Limitation, stated honestly: this dictionary lives in ONE process's
    memory. If RideFlow ever runs as multiple app instances behind a load
    balancer, a connection registered on instance A is invisible to
    instance B — that's the exact problem Redis Pub/Sub fanout solves,
    which we are NOT building yet because we only run one instance.
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, connection_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    def disconnect(self, connection_id: str):
        self.active_connections.pop(connection_id, None)

    async def send_to(self, connection_id: str, message: dict):
        """
        Pushes a message to one specific connection, if it's currently
        connected. Silently does nothing if that id isn't connected right
        now — e.g. a rider who closed their app. This is a fire-and-forget
        push, not a guaranteed-delivery system (no retry, no queue).
        """
        websocket = self.active_connections.get(connection_id)
        if websocket:
            await websocket.send_json(message)


# Two separate registries — a driver_id and a rider_id could theoretically
# collide if we used one shared dict, so keep them fully independent.
driver_manager = ConnectionManager()
rider_manager = ConnectionManager()
