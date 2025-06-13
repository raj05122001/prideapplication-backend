# router.py
from fastapi import APIRouter, Depends,WebSocket, WebSocketDisconnect, HTTPException
from typing import List
from sqlalchemy.orm import Session
from db.connection import get_db
from db.schema import OptionOut,  OptionCreate, OptionUpdate
from db.models import Option
import asyncio

router = APIRouter(prefix="/researcher", tags=["researcher"])

def get_option(db: Session, option_id: int):
    opt = db.query(Option).filter(Option.id == option_id).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Option not found")
    return opt

def get_options(db: Session, skip: int = 0, limit: int = 100) -> List[Option]:
    return db.query(Option).offset(skip).limit(limit).all()

def create_option(db: Session, option: OptionCreate):
    db_opt = Option(**option.dict())
    db.add(db_opt)
    db.commit()
    db.refresh(db_opt)
    return db_opt

def update_option(db: Session, option_id: int, upd: OptionUpdate):
    db_opt = get_option(db, option_id)
    for field, value in upd.dict(exclude_unset=True).items():
        setattr(db_opt, field, value)
    db.commit()
    db.refresh(db_opt)
    return db_opt

@router.post("/", response_model=OptionOut)
def add_option(option: OptionCreate, db: Session = Depends(get_db)):
    return create_option(db, option)

@router.get("/", response_model=List[OptionOut])
def list_options(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_options(db, skip=skip, limit=limit)

@router.get("/{option_id}", response_model=OptionOut)
def read_option(option_id: int, db: Session = Depends(get_db)):
    return get_option(db, option_id)

@router.put("/{option_id}", response_model=OptionOut)
def edit_option(option_id: int, upd: OptionUpdate, db: Session = Depends(get_db)):
    return update_option(db, option_id, upd)

@router.websocket("/ws")
async def websocket_options(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket endpoint that listens for text commands:
      - 'get_all' -> sends list of all options
      - 'get_<id>' -> sends single option by id
    """
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == 'get_all':
                opts = get_options(db)
                data = [OptionOut.from_orm(o).dict() for o in opts]
                await websocket.send_json(data)
            elif msg.startswith('get_'):
                try:
                    _, id_str = msg.split('_', 1)
                    option = get_option(db, int(id_str))
                    await websocket.send_json(OptionOut.from_orm(option).dict())
                except (ValueError, HTTPException) as e:
                    await websocket.send_json({"error": str(e)})
            else:
                # ignore or echo
                await websocket.send_text(f"Unknown command: {msg}")
            # small pause if needed
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        # client disconnected
        pass