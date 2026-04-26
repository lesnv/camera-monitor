import os
import uuid
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Text,
    ForeignKey, DateTime, Float, func
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

# ------------------------------
# Конфигурация (как в старом проекте)
# ------------------------------
DATABASE_URL = "sqlite:////app/data/camera.db"
UPLOAD_DIR = "/app/uploads/resized"
os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ------------------------------
# Модели SQLAlchemy (расширенные)
# ------------------------------
class OrangePi(Base):
    __tablename__ = "orange_pis"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False, unique=True)
    api_key = Column(String, nullable=True, default="default_key")
    # Новые поля
    status = Column(String, default="offline")          # online/offline
    last_heartbeat = Column(DateTime, default=func.now())
    cpu_usage = Column(Float, default=0.0)
    ram_usage = Column(Float, default=0.0)
    disk_usage = Column(Float, default=0.0)
    temperature = Column(Float, default=0.0)
    # Старое поле (можно не трогать, но теперь не используется)
    last_seen = Column(DateTime, default=func.now())
    cameras = relationship("Camera", back_populates="orange_pi")

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    orange_pi_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    rtsp_url = Column(String, nullable=True)
    # Новые поля
    ip_address = Column(String, nullable=True)          # IP камеры
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    sensitivity = Column(Integer, default=50)           # 1..100
    detection_interval = Column(Integer, default=5)     # секунды
    analysis_prompt = Column(Text, default="")
    report_prompt = Column(Text, default="")
    screenshot_quality = Column(Integer, default=640)   # высота кадра
    # Старые поля (оставлены для совместимости)
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
    # Новое поле
    description = Column(Text, nullable=True)            # описание от VLM
    # Старые поля
    ollama_response = Column(Text, nullable=True)
    motion_level = Column(Integer, default=0)
    is_danger = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    camera = relationship("Camera", back_populates="screenshots")

Base.metadata.create_all(bind=engine)

# ------------------------------
# Pydantic схемы (расширенные)
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

class OrangePiOut(BaseModel):
    id: int
    name: str
    ip: str
    api_key: str
    status: str
    last_heartbeat: Optional[datetime] = None
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    temperature: float
    camera_count: int = 0
    class Config:
        orm_mode = True
        from_attributes = True

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

class CameraOut(BaseModel):
    id: int
    name: str
    orange_pi_id: int
    rtsp_url: Optional[str]
    ip_address: Optional[str]
    username: Optional[str]   # ⚠️ пароль не возвращаем в открытом виде
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

class ScreenshotOut(BaseModel):
    id: int
    camera_id: int
    filename: str
    url: str
    description: Optional[str] = None
    motion_level: int
    created_at: datetime
    class Config:
        orm_mode = True
        from_attributes = True

# ------------------------------
# FastAPI приложение
# ------------------------------
app = FastAPI(title="Camera Monitor v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ------------------------------
# Вспомогательные зависимости
# ------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# Heartbeat-логика (проверка при каждом запросе списка)
# ------------------------------
def check_heartbeat(pi):
    if pi.last_heartbeat and (datetime.utcnow() - pi.last_heartbeat) > timedelta(minutes=2):
        pi.status = "offline"
    elif pi.last_heartbeat:
        pi.status = "online"

# ------------------------------
# Эндпоинты Orange Pi
# ------------------------------
@app.get("/api/orangepi", response_model=List[OrangePiOut])
def list_orangepi():
    db = SessionLocal()
    try:
        pis = db.query(OrangePi).all()
        result = []
        for pi in pis:
            check_heartbeat(pi)
            camera_count = len(pi.cameras)
            result.append(OrangePiOut(
                id=pi.id, name=pi.name, ip=pi.ip, api_key=pi.api_key,
                status=pi.status, last_heartbeat=pi.last_heartbeat,
                cpu_usage=pi.cpu_usage, ram_usage=pi.ram_usage,
                disk_usage=pi.disk_usage, temperature=pi.temperature,
                camera_count=camera_count
            ))
        db.commit()
        return result
    finally:
        db.close()

@app.post("/api/orangepi", response_model=OrangePiOut)
def create_orangepi(data: OrangePiCreate):
    db = SessionLocal()
    try:
        pi = OrangePi(name=data.name, ip=data.ip, api_key=data.api_key)
        db.add(pi)
        db.commit()
        db.refresh(pi)
        return OrangePiOut(
            id=pi.id, name=pi.name, ip=pi.ip, api_key=pi.api_key,
            status=pi.status, last_heartbeat=pi.last_heartbeat,
            cpu_usage=pi.cpu_usage, ram_usage=pi.ram_usage,
            disk_usage=pi.disk_usage, temperature=pi.temperature,
            camera_count=0
        )
    finally:
        db.close()

@app.get("/api/orangepi/{pi_id}", response_model=OrangePiOut)
def get_orangepi(pi_id: int):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        check_heartbeat(pi)
        camera_count = len(pi.cameras)
        db.commit()
        return OrangePiOut(
            id=pi.id, name=pi.name, ip=pi.ip, api_key=pi.api_key,
            status=pi.status, last_heartbeat=pi.last_heartbeat,
            cpu_usage=pi.cpu_usage, ram_usage=pi.ram_usage,
            disk_usage=pi.disk_usage, temperature=pi.temperature,
            camera_count=camera_count
        )
    finally:
        db.close()

@app.post("/api/orangepi/{pi_id}/status")
def update_orangepi_status(pi_id: int, data: OrangePiStatusUpdate):
    db = SessionLocal()
    try:
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
    finally:
        db.close()

# ------------------------------
# Эндпоинты камер
# ------------------------------
@app.post("/api/orangepi/{pi_id}/cameras", response_model=CameraOut)
def create_camera_for_pi(pi_id: int, data: CameraCreate = Body(...)):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        # Собираем данные с новыми полями
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
            # если переданы старые поля, используем их, иначе значения по умолчанию
            motion_interval=data.motion_interval or 10,
            motion_sensitivity=data.motion_sensitivity or 50,
            resolution=data.resolution or "640",
            enabled=data.enabled if data.enabled is not None else True
        )
        db.add(cam)
        db.commit()
        db.refresh(cam)
        return cam
    finally:
        db.close()

@app.get("/api/orangepi/{pi_id}/cameras", response_model=List[CameraOut])
def list_cameras_for_pi(pi_id: int):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        return pi.cameras
    finally:
        db.close()

@app.get("/api/cameras", response_model=List[CameraOut])
def list_cameras():
    db = SessionLocal()
    try:
        return db.query(Camera).all()
    finally:
        db.close()

# ------------------------------
# Загрузка и просмотр скриншотов
# ------------------------------
@app.post("/api/upload/{camera_id}")
async def upload_photo(
    camera_id: int,
    file: UploadFile = File(...),
    motion_level: int = Form(0),
    description: Optional[str] = Form(None)
):
    db = SessionLocal()
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        db.close()

@app.get("/api/screenshots", response_model=dict)
def list_screenshots(
    camera_id: Optional[int] = None,
    date: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    db = SessionLocal()
    try:
        query = db.query(Screenshot)
        if camera_id is not None:
            query = query.filter(Screenshot.camera_id == camera_id)
        if date:
            query = query.filter(Screenshot.created_at >= date)
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
    finally:
        db.close()

# ------------------------------
# Статические маршруты (до монтирования общей статики)
# ------------------------------
@app.get("/")
def root():
    return FileResponse("/app/static/index.html")

@app.get("/device/{pi_id}")
def device_page(pi_id: int):
    return FileResponse("/app/static/device.html")

# ------------------------------
# Монтирование статики (в самом конце)
# ------------------------------
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

# Если остались другие пути, будет попытка отдать статический файл
@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # Пробуем вернуть из статики
    static_file = os.path.join("/app/static", full_path)
    if os.path.isfile(static_file):
        return FileResponse(static_file)
    raise HTTPException(status_code=404)