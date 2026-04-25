# Test auto deploy 2026-04-26
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime, func, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from starlette.responses import FileResponse
import os, uuid, shutil

DATABASE_URL = "sqlite:////app/data/camera.db"
UPLOAD_DIR = "/app/uploads/resized"
os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class OrangePi(Base):
    __tablename__ = "orange_pis"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False, unique=True)
    api_key = Column(String, nullable=True, default="default_key")
    last_seen = Column(DateTime, default=func.now())
    cameras = relationship("Camera", back_populates="orange_pi")

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    orange_pi_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    rtsp_url = Column(String, nullable=True)
    motion_interval = Column(Integer, default=10)
    motion_sensitivity = Column(Integer, default=50)
    detection_threshold = Column(Float, default=0.3)
    min_motion_area = Column(Integer, default=500)
    resolution = Column(String, default="640")
    analysis_prompt = Column(Text, nullable=True)
    report_prompt = Column(Text, nullable=True)
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
    ollama_response = Column(Text, nullable=True)
    motion_level = Column(Integer, default=0)
    is_danger = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    camera = relationship("Camera", back_populates="screenshots")

Base.metadata.create_all(bind=engine)

class OrangePiCreate(BaseModel):
    name: str
    ip: str
    api_key: str = "default_key"

class CameraCreate(BaseModel):
    name: str
    orange_pi_id: int
    rtsp_url: str = None
    motion_interval: int = 10
    motion_sensitivity: int = 50
    detection_threshold: float = 0.3
    min_motion_area: int = 500
    resolution: str = "640"
    enabled: bool = True

app = FastAPI(title="Camera Monitor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# === ВСЕ API маршруты — СНАЧАЛА! ===

@app.get("/api/orangepi")
def list_orangepi():
    db = SessionLocal()
    try: return db.query(OrangePi).all()
    finally: db.close()

@app.post("/api/orangepi")
def create_orangepi( OrangePiCreate):
    db = SessionLocal()
    try:
        pi = OrangePi(name=data.name, ip=data.ip, api_key=data.api_key)
        db.add(pi); db.commit(); db.refresh(pi)
        return pi
    finally: db.close()

@app.get("/api/orangepi/{pi_id}")
def get_orangepi(pi_id: int):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi: raise HTTPException(404, "Orange Pi not found")
        return pi
    finally: db.close()

@app.post("/api/orangepi/{pi_id}/cameras")
def create_camera_for_pi(pi_id: int, data: CameraCreate = Body(...)):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi: raise HTTPException(404, "Orange Pi not found")
        cam = Camera(**data.dict(), orange_pi_id=pi_id)
        db.add(cam); db.commit(); db.refresh(cam)
        return cam
    finally: db.close()

@app.get("/api/cameras")
def list_cameras():
    db = SessionLocal()
    try: return db.query(Camera).all()
    finally: db.close()

@app.post("/api/cameras")
def create_camera( CameraCreate):
    db = SessionLocal()
    try:
        cam = Camera(**data.dict())
        db.add(cam); db.commit(); db.refresh(cam)
        return cam
    finally: db.close()

@app.get("/api/screenshots")
def list_screenshots(date: str = None, page: int = 1, limit: int = 20):
    db = SessionLocal()
    try:
        query = db.query(Screenshot)
        if date: query = query.filter(Screenshot.created_at >= date)
        items = query.order_by(Screenshot.created_at.desc()).offset((page-1)*limit).limit(limit).all()
        total = query.count()
        return {"items": [{"id": s.id, "filename": s.filename, "url": f"/uploads/resized/{s.filename}", "created_at": s.created_at, "motion_level": s.motion_level} for s in items], "total": total, "page": page, "total_pages": (total + limit - 1) // limit}
    finally: db.close()

@app.post("/api/upload/{camera_id}")
async def upload_photo(camera_id: int, file: UploadFile = File(...), motion_level: int = Form(0)):
    db = SessionLocal()
    try:
        cam = db.query(Camera).filter(Camera.id == camera_id, Camera.enabled == True).first()
        if not cam: raise HTTPException(404, "Camera disabled/not found")
        filename = f"cam{camera_id}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f: shutil.copyfileobj(file.file, f)
        shot = Screenshot(camera_id=camera_id, filename=filename, original_path=filepath, resized_path=filepath, motion_level=motion_level)
        db.add(shot); db.commit()
        return {"status": "ok", "filename": filename, "message": "Photo saved"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))
    finally: db.close()

# === Статические файлы — В САМОМ КОНЦЕ! ===
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
