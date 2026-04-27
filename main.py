import os
import uuid
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Text,
    ForeignKey, DateTime, Float, func
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base, Session

# ------------------------------
# Конфигурация
# ------------------------------
DATABASE_URL = "sqlite:////app/data/camera.db"
UPLOAD_DIR = "/app/uploads/resized"
os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ------------------------------
# Модели SQLAlchemy
# ------------------------------
class OrangePi(Base):
    __tablename__ = "orange_pis"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False, unique=True)
    api_key = Column(String, nullable=True, default="default_key")
    status = Column(String, default="offline")
    last_heartbeat = Column(DateTime, default=func.now())
    cpu_usage = Column(Float, default=0.0)
    ram_usage = Column(Float, default=0.0)
    disk_usage = Column(Float, default=0.0)
    temperature = Column(Float, default=0.0)
    last_seen = Column(DateTime, default=func.now())
    cameras = relationship("Camera", back_populates="orange_pi")

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    orange_pi_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    rtsp_url = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    sensitivity = Column(Integer, default=50)
    detection_interval = Column(Integer, default=5)
    analysis_prompt = Column(Text, default="")
    report_prompt = Column(Text, default="")
    screenshot_quality = Column(Integer, default=640)
    motion_interval = Column(Integer, default=10)
    motion_sensitivity = Column(Integer, default=50)
    detection_threshold = Column(Float, default=0.3)
    min_motion_area = Column(Integer, default=500)
    resolution = Column(String, default="640")
    analysis_model = Column(String, default="qwen2.5vl:3b")
    report_model = Column(String, default="qwen2.5vl:3b")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    orange_pi = relationship("OrangePi", back_populates="cameras")
    screenshots = relationship("Screenshot", back_populates="camera")

class Screenshot(Base):
    __tablename__ = "screenshots"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    filename = Column(String, nullable=False)
    original_path = Column(String, nullable=True)
    resized_path = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    ollama_response = Column(Text, nullable=True)
    motion_level = Column(Integer, default=0)
    is_danger = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    camera = relationship("Camera", back_populates="screenshots")

class Command(Base):
    __tablename__ = "commands"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    command = Column(String, default="snapshot")
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)

# ------------------------------
# Pydantic схемы
# ------------------------------
class OrangePiCreate(BaseModel):
    name: str
    ip: str
    api_key: str = "default_key"

class OrangePiStatusUpdate(BaseModel):
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    temperature: float

class CameraCreate(BaseModel):
    name: str
    rtsp_url: Optional[str] = None
    ip_address: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    sensitivity: int = 50
    detection_interval: int = 5
    analysis_prompt: str = ""
    report_prompt: str = ""
    screenshot_quality: int = 640
    motion_interval: Optional[int] = None
    motion_sensitivity: Optional[int] = None
    resolution: Optional[str] = None
    enabled: Optional[bool] = None

# ------------------------------
# FastAPI приложение
# ------------------------------
app = FastAPI(title="Camera Monitor v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_heartbeat(pi):
    if pi.last_heartbeat and (datetime.utcnow() - pi.last_heartbeat) > timedelta(minutes=2):
        pi.status = "offline"
    elif pi.last_heartbeat:
        pi.status = "online"

# ============================================================
# Эндпоинты Orange Pi
# ============================================================
@app.get("/api/orangepi")
def list_orangepi(db: Session = Depends(get_db)):
    pis = db.query(OrangePi).all()
    result = []
    for pi in pis:
        check_heartbeat(pi)
        camera_count = len(pi.cameras)
        result.append({
            "id": pi.id,
            "name": pi.name,
            "ip": pi.ip,
            "api_key": pi.api_key,
            "status": pi.status,
            "last_heartbeat": pi.last_heartbeat.isoformat() if pi.last_heartbeat else None,
            "cpu_usage": pi.cpu_usage,
            "ram_usage": pi.ram_usage,
            "disk_usage": pi.disk_usage,
            "temperature": pi.temperature,
            "camera_count": camera_count
        })
    db.commit()
    return result

@app.post("/api/orangepi")
def create_orangepi(data: OrangePiCreate, db: Session = Depends(get_db)):
    pi = OrangePi(**data.dict())
    db.add(pi)
    db.commit()
    db.refresh(pi)
    return {
        "id": pi.id,
        "name": pi.name,
        "ip": pi.ip,
        "api_key": pi.api_key,
        "status": pi.status,
        "last_heartbeat": pi.last_heartbeat.isoformat() if pi.last_heartbeat else None,
        "cpu_usage": pi.cpu_usage,
        "ram_usage": pi.ram_usage,
        "disk_usage": pi.disk_usage,
        "temperature": pi.temperature,
        "camera_count": 0
    }

@app.get("/api/orangepi/{pi_id}")
def get_orangepi(pi_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi:
        raise HTTPException(404, "Orange Pi not found")
    check_heartbeat(pi)
    camera_count = len(pi.cameras)
    db.commit()
    return {
        "id": pi.id,
        "name": pi.name,
        "ip": pi.ip,
        "api_key": pi.api_key,
        "status": pi.status,
        "last_heartbeat": pi.last_heartbeat.isoformat() if pi.last_heartbeat else None,
        "cpu_usage": pi.cpu_usage,
        "ram_usage": pi.ram_usage,
        "disk_usage": pi.disk_usage,
        "temperature": pi.temperature,
        "camera_count": camera_count
    }

@app.post("/api/orangepi/{pi_id}/status")
def update_orangepi_status(pi_id: int, data: OrangePiStatusUpdate, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi:
        raise HTTPException(404, "Orange Pi not found")
    pi.cpu_usage = data.cpu_usage
    pi.ram_usage = data.ram_usage
    pi.disk_usage = data.disk_usage
    pi.temperature = data.temperature
    pi.status = "online"
    pi.last_heartbeat = datetime.utcnow()
    db.commit()
    return {"status": "ok"}

# ============================================================
# Эндпоинты камер
# ============================================================
class CameraOut(BaseModel):
    id: int
    name: str
    orange_pi_id: int
    rtsp_url: Optional[str]
    ip_address: Optional[str]
    username: Optional[str]
    sensitivity: int
    detection_interval: int
    analysis_prompt: str
    report_prompt: str
    screenshot_quality: int
    enabled: bool
    created_at: datetime
    class Config:
        orm_mode = True
        from_attributes = True

@app.post("/api/orangepi/{pi_id}/cameras", response_model=CameraOut)
def create_camera_for_pi(pi_id: int, data: CameraCreate = Body(...), db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi:
        raise HTTPException(404, "Orange Pi not found")
    cam = Camera(
        name=data.name,
        orange_pi_id=pi_id,
        rtsp_url=data.rtsp_url,
        ip_address=data.ip_address,
        username=data.username,
        password=data.password,
        sensitivity=data.sensitivity,
        detection_interval=data.detection_interval,
        analysis_prompt=data.analysis_prompt,
        report_prompt=data.report_prompt,
        screenshot_quality=data.screenshot_quality,
        motion_interval=data.motion_interval or 10,
        motion_sensitivity=data.motion_sensitivity or 50,
        resolution=data.resolution or "640",
        enabled=data.enabled if data.enabled is not None else True
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam

@app.get("/api/orangepi/{pi_id}/cameras", response_model=List[CameraOut])
def list_cameras_for_pi(pi_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi:
        raise HTTPException(404, "Orange Pi not found")
    return pi.cameras

@app.put("/api/cameras/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: int, data: CameraCreate = Body(...), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(cam, key, value)
    db.commit()
    db.refresh(cam)
    return cam

@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    db.delete(cam)
    db.commit()
    return {"status": "deleted"}

# ============================================================
# Система команд
# ============================================================
@app.post("/api/cameras/{camera_id}/snapshot")
def request_snapshot(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    cmd = Command(device_id=cam.orange_pi_id, camera_id=camera_id, command="snapshot")
    db.add(cmd)
    db.commit()
    return {"status": "queued", "message": "Snapshot command created"}

@app.get("/api/orangepi/{pi_id}/commands")
def get_pending_commands(pi_id: int, db: Session = Depends(get_db)):
    commands = db.query(Command).filter(
        Command.device_id == pi_id,
        Command.status == "pending"
    ).all()
    return [{"id": c.id, "camera_id": c.camera_id, "command": c.command} for c in commands]

@app.put("/api/commands/{command_id}/complete")
def complete_command(command_id: int, db: Session = Depends(get_db)):
    cmd = db.query(Command).filter(Command.id == command_id).first()
    if not cmd:
        raise HTTPException(404, "Command not found")
    cmd.status = "completed"
    db.commit()
    return {"status": "ok"}

# ============================================================
# Загрузка и просмотр скриншотов
# ============================================================
@app.post("/api/upload/{camera_id}")
async def upload_photo(
    camera_id: int,
    file: UploadFile = File(...),
    motion_level: int = Form(0),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    cam = db.query(Camera).filter(Camera.id == camera_id, Camera.enabled == True).first()
    if not cam:
        raise HTTPException(404, "Camera disabled/not found")
    filename = f"cam{camera_id}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    shot = Screenshot(
        camera_id=camera_id,
        filename=filename,
        original_path=filepath,
        resized_path=filepath,
        motion_level=motion_level,
        description=description
    )
    db.add(shot)
    db.commit()
    return {"status": "ok", "filename": filename, "message": "Photo saved"}

@app.get("/api/screenshots")
def list_screenshots(
    camera_id: Optional[int] = None,
    start: Optional[str] = Query(None, description="Начальная дата (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="Конечная дата (YYYY-MM-DD)"),
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(Screenshot)
    if camera_id is not None:
        query = query.filter(Screenshot.camera_id == camera_id)
    if start:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            query = query.filter(Screenshot.created_at >= start_dt)
        except ValueError:
            raise HTTPException(400, "Invalid start date format. Use YYYY-MM-DD")
    if end:
        try:
            end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Screenshot.created_at < end_dt)
        except ValueError:
            raise HTTPException(400, "Invalid end date format. Use YYYY-MM-DD")
    total = query.count()
    items = (
        query.order_by(Screenshot.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": s.id,
                "camera_id": s.camera_id,
                "filename": s.filename,
                "url": f"/uploads/resized/{s.filename}",
                "description": s.description,
                "motion_level": s.motion_level,
                "created_at": s.created_at.isoformat()
            }
            for s in items
        ],
        "total": total,
        "page": page,
        "total_pages": (total + limit - 1) // limit
    }

# ============================================================
# Статические маршруты
# ============================================================
@app.get("/")
def root():
    return FileResponse("/app/static/index.html")

@app.get("/device/{pi_id}")
def device_page(pi_id: int):
    return FileResponse("/app/static/device.html")

app.mount("/uploads/resized", StaticFiles(directory=UPLOAD_DIR), name="uploads_resized")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")