from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import driver_manager, rider_manager

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/driver/{driver_id}")
async def driver_websocket(websocket: WebSocket, driver_id: str):
    await driver_manager.connect(driver_id, websocket)
    try:
        while True:
            # We don't actually need anything FROM the driver right now —
            # this loop's real job is just to detect disconnection.
            # receive_text() blocks here until either a message arrives
            # or the client disconnects (which raises WebSocketDisconnect).
            await websocket.receive_text()
    except WebSocketDisconnect:
        driver_manager.disconnect(driver_id)


@router.websocket("/ws/rider/{rider_id}")
async def rider_websocket(websocket: WebSocket, rider_id: str):
    await rider_manager.connect(rider_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        rider_manager.disconnect(rider_id)
