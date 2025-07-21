from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from typing import List, Dict
from collections import defaultdict
from sqlalchemy.orm import Session
from db.connection import get_db
from db.schema import OptionOut, OptionCreate, OptionUpdate
from db.models import Option, UserDetails
import json

from fastapi.responses import StreamingResponse
import httpx

router = APIRouter(prefix="/researcher", tags=["researcher"])

# --- Connection manager for WebSockets, grouped by service ---
class ConnectionManager:
    def __init__(self):
        # service_name → list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, service: str):
        await websocket.accept()
        self.active_connections[service].append(websocket)

    def disconnect(self, websocket: WebSocket, service: str):
        if websocket in self.active_connections.get(service, []):
            self.active_connections[service].remove(websocket)

    async def broadcast(self, message: dict, service: str):
        data = json.dumps(message)
        for connection in self.active_connections.get(service, []):
            await connection.send_text(data)

manager = ConnectionManager()

# --- DB helpers ---
def get_option(db: Session, option_id: int) -> Option:
    opt = db.query(Option).filter(Option.id == option_id).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Option not found")
    return opt

def get_options(db: Session, skip: int = 0, limit: int = 100) -> List[Option]:
    return db.query(Option).offset(skip).limit(limit).all()

def create_option(db: Session, option: OptionCreate) -> Option:
    db_opt = Option(**option.dict())
    db.add(db_opt)
    db.commit()
    db.refresh(db_opt)
    return db_opt

def update_option(db: Session, option_id: int, upd: OptionUpdate) -> Option:
    db_opt = get_option(db, option_id)
    for field, value in upd.dict(exclude_unset=True).items():
        setattr(db_opt, field, value)
    db.commit()
    db.refresh(db_opt)
    return db_opt

# --- CRUD endpoints with broadcasting ---
@router.post("/", response_model=OptionOut)
async def add_option(option: OptionCreate, db: Session = Depends(get_db)):
    opt = create_option(db, option)
    payload = {
        "action": "created",
        "option": OptionOut.from_orm(opt).model_dump(mode="json")
    }
    for svc in opt.service:
        await manager.broadcast(payload, service=svc)
    return opt

@router.get("/", response_model=List[OptionOut])
def list_options(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_options(db, skip=skip, limit=limit)

@router.get("/{phone}", response_model=List[OptionOut])
def read_options_by_user(
    phone: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    user = db.query(UserDetails).filter(UserDetails.phone_number == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return (
        db.query(Option)
          .filter(Option.service.op('&&')(user.service))
          .order_by(Option.timestamp.desc())
          .offset(skip)
          .limit(limit)
          .all()
    )

@router.put("/{option_id}", response_model=OptionOut)
async def edit_option(option_id: int, upd: OptionUpdate, db: Session = Depends(get_db)):
    opt = update_option(db, option_id, upd)
    payload = {
        "action": "updated",
        "option": OptionOut.from_orm(opt).model_dump(mode="json")
    }
    for svc in opt.service:
        await manager.broadcast(payload, service=svc)
    return opt

@router.delete("/{option_id}", response_model=OptionOut)
async def delete_option(option_id: int, db: Session = Depends(get_db)):
    opt = get_option(db, option_id)
    payload = OptionOut.from_orm(opt).model_dump(mode="json")
    services = opt.service

    db.delete(opt)
    db.commit()

    for svc in services:
        await manager.broadcast({
            "action": "deleted",
            "option": payload
        }, service=svc)

    return opt

# --- WebSocket Endpoint for Live Updates ---
@router.websocket("/ws/options/{service}")
async def websocket_options_endpoint(websocket: WebSocket, service: str):
    """
    Subscribe here to receive live updates for a given service.
    Messages will be of the form:
      { action: "created"|"updated"|"deleted", option: { ... } }
    """
    await manager.connect(websocket, service)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, service)

@router.get("/files/{file_key}", summary="Proxy a file from CloudFront")
async def fetch_researcher_file(file_key: str):
    # 1️⃣ Build the CF URL
    url = f"https://d12p872xp7spmg.cloudfront.net/{file_key}"

    # 2️⃣ Stream the remote response
    async with httpx.AsyncClient(timeout=None) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="File not found")

        # 3️⃣ Grab the remote content-type (fallback to octet-stream)
        content_type = resp.headers.get("content-type", "application/octet-stream")

        # 4️⃣ Return a streaming response
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type=content_type,
            headers={
                # Optional: force download filename
                "Content-Disposition": f'attachment; filename="{file_key}"'
            }
        )
