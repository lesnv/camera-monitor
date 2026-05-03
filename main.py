import os, uuid, shutil, requests, base64, json, threading, time, socket, ipaddress, io, hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from PIL import Image
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime, Float, func
from sqlalchemy.orm import sessionmaker, relationship, declarative_base, Session

DATABASE_URL = "sqlite:////app/data/camera.db"
UPLOAD_DIR = "/app/uploads/resized"
AGENT_VERSIONS_DIR = "/app/agent_versions"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AGENT_VERSIONS_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    analysis_enabled = Column(Boolean, default=True)
    agent_version = Column(String, nullable=True)
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
    external_api_url = Column(String, nullable=True)
    external_api_key = Column(String, nullable=True)
    external_model_name = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    motion_detection_enabled = Column(Boolean, default=True)
    detection_method = Column(String, default="simple")
    periodic_snapshot_enabled = Column(Boolean, default=False)
    periodic_interval = Column(Integer, default=60)
    mog2_var_threshold = Column(Integer, default=100)
    knn_dist2_threshold = Column(Integer, default=400)
    debug_motion = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    orange_pi = relationship("OrangePi", back_populates="cameras")
    screenshots = relationship("Screenshot", back_populates="camera", cascade="all, delete-orphan")

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
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True)
    command = Column(String, default="snapshot")
    params = Column(Text, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=func.now())

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    report_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

class ScanResult(Base):
    __tablename__ = "scan_results"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("orange_pis.id"), nullable=False)
    ip_address = Column(String, nullable=False)
    rtsp_url = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    added = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)

class OrangePiCreate(BaseModel): name: str; ip: str; api_key: str = "default_key"
class OrangePiStatusUpdate(BaseModel):
    cpu_usage: float; ram_usage: float; disk_usage: float; temperature: float
    ip: Optional[str] = None; agent_version: Optional[str] = None
class OrangePiPatch(BaseModel): analysis_enabled: Optional[bool] = None
class CameraCreate(BaseModel):
    name: str; rtsp_url: Optional[str] = None; ip_address: Optional[str] = None; username: Optional[str] = None; password: Optional[str] = None
    sensitivity: int = 50; detection_interval: int = 5; analysis_prompt: str = ""; report_prompt: str = ""
    screenshot_quality: int = 640
    analysis_model: Optional[str] = None; report_model: Optional[str] = None
    external_api_url: Optional[str] = None; external_api_key: Optional[str] = None; external_model_name: Optional[str] = None
    motion_detection_enabled: Optional[bool] = None; detection_method: Optional[str] = None
    periodic_snapshot_enabled: Optional[bool] = None; periodic_interval: Optional[int] = None
    mog2_var_threshold: Optional[int] = None; knn_dist2_threshold: Optional[int] = None; debug_motion: Optional[bool] = None

class CameraUpdate(BaseModel):
    name: Optional[str] = None; rtsp_url: Optional[str] = None; ip_address: Optional[str] = None; username: Optional[str] = None; password: Optional[str] = None
    sensitivity: Optional[int] = None; detection_interval: Optional[int] = None; analysis_prompt: Optional[str] = None; report_prompt: Optional[str] = None
    screenshot_quality: Optional[int] = None
    analysis_model: Optional[str] = None; report_model: Optional[str] = None
    external_api_url: Optional[str] = None; external_api_key: Optional[str] = None; external_model_name: Optional[str] = None
    motion_detection_enabled: Optional[bool] = None; detection_method: Optional[str] = None
    periodic_snapshot_enabled: Optional[bool] = None; periodic_interval: Optional[int] = None
    mog2_var_threshold: Optional[int] = None; knn_dist2_threshold: Optional[int] = None; debug_motion: Optional[bool] = None

class CameraOut(BaseModel):
    id: int; name: str; orange_pi_id: int; rtsp_url: Optional[str]; ip_address: Optional[str]; username: Optional[str]
    sensitivity: int; detection_interval: int; analysis_prompt: str; report_prompt: str; screenshot_quality: int
    enabled: bool; created_at: datetime
    analysis_model: Optional[str]; report_model: Optional[str]
    motion_detection_enabled: bool; detection_method: str; periodic_snapshot_enabled: bool; periodic_interval: int
    mog2_var_threshold: int; knn_dist2_threshold: int; debug_motion: bool
    class Config: orm_mode = True; from_attributes = True

class ScanCommandParams(BaseModel): target_network: str = "192.168.1.0/24"; username: str = "admin"; password: str = "admin"

app = FastAPI(title="Camera Monitor v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def check_heartbeat(pi):
    if pi.last_heartbeat and (datetime.utcnow() - pi.last_heartbeat) > timedelta(minutes=2):
        pi.status = "offline"
    elif pi.last_heartbeat: pi.status = "online"

@app.get("/api/orangepi")
def list_orangepi(db: Session = Depends(get_db)):
    pis = db.query(OrangePi).all()
    result = []
    for pi in pis:
        check_heartbeat(pi)
        result.append({
            "id": pi.id, "name": pi.name, "ip": pi.ip,
            "status": pi.status, "last_heartbeat": pi.last_heartbeat.isoformat() if pi.last_heartbeat else None,
            "cpu_usage": pi.cpu_usage, "ram_usage": pi.ram_usage, "disk_usage": pi.disk_usage, "temperature": pi.temperature,
            "camera_count": len(pi.cameras), "analysis_enabled": pi.analysis_enabled, "agent_version": pi.agent_version or "—"
        })
    db.commit()
    return result

@app.post("/api/orangepi")
def create_orangepi(data: OrangePiCreate, db: Session = Depends(get_db)):
    pi = OrangePi(**data.dict()); db.add(pi); db.commit(); db.refresh(pi)
    return {"id": pi.id}

@app.get("/api/orangepi/{pi_id}")
def get_orangepi(pi_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi: raise HTTPException(404)
    check_heartbeat(pi); db.commit()
    return {"id": pi.id, "name": pi.name, "ip": pi.ip, "status": pi.status, "analysis_enabled": pi.analysis_enabled, "agent_version": pi.agent_version or "—"}

@app.post("/api/orangepi/{pi_id}/status")
def update_orangepi_status(pi_id: int, data: OrangePiStatusUpdate, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi: raise HTTPException(404)
    # Если приходит новый IP, проверяем, не занят ли он другим устройством.
    # Если занят, просто не обновляем IP, чтобы не было ошибки.
    if data.ip and data.ip != pi.ip:
        conflict = db.query(OrangePi).filter(OrangePi.ip == data.ip, OrangePi.id != pi_id).first()
        if conflict:
            # IP занят, пропускаем обновление IP, но разрешаем обновить остальные поля
            data.ip = None
    # Обновляем только те поля, которые не None
    for key, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(pi, key, value)
    pi.status = "online"; pi.last_heartbeat = datetime.utcnow()
    db.commit(); return {"status": "ok"}

@app.patch("/api/orangepi/{pi_id}")
def patch_orangepi(pi_id: int, data: OrangePiPatch, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi: raise HTTPException(404)
    if data.analysis_enabled is not None: pi.analysis_enabled = data.analysis_enabled
    db.commit(); return {"analysis_enabled": pi.analysis_enabled}

@app.post("/api/orangepi/{device_id}/sync")
def request_sync(device_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == device_id).first()
    if not pi: raise HTTPException(404)
    cmd = Command(device_id=device_id, command="sync"); db.add(cmd); db.commit()
    return {"status": "queued"}

@app.post("/api/orangepi/{device_id}/restart")
def request_restart(device_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == device_id).first()
    if not pi: raise HTTPException(404)
    cmd = Command(device_id=device_id, command="restart"); db.add(cmd); db.commit()
    return {"status": "queued"}

@app.post("/api/orangepi/{device_id}/scan")
def start_scan(device_id: int, params: ScanCommandParams, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == device_id).first()
    if not pi: raise HTTPException(404)
    cmd = Command(device_id=device_id, command="scan_network", params=json.dumps(params.dict())); db.add(cmd); db.commit()
    return {"status": "queued"}

@app.get("/api/orangepi/{pi_id}/commands")
def get_pending_commands(pi_id: int, db: Session = Depends(get_db)):
    return [{"id": c.id, "camera_id": c.camera_id, "command": c.command, "params": c.params} for c in db.query(Command).filter(Command.device_id == pi_id, Command.status == "pending").all()]

@app.put("/api/commands/{command_id}/complete")
def complete_command(command_id: int, db: Session = Depends(get_db)):
    cmd = db.query(Command).filter(Command.id == command_id).first()
    if not cmd: raise HTTPException(404)
    cmd.status = "completed"; db.commit(); return {"status": "ok"}

@app.post("/api/cameras/{camera_id}/snapshot")
def request_snapshot(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam: raise HTTPException(404)
    cmd = Command(device_id=cam.orange_pi_id, camera_id=camera_id, command="snapshot")
    db.add(cmd); db.commit()
    return {"status": "queued"}

@app.post("/api/orangepi/{pi_id}/cameras", response_model=CameraOut)
def create_camera_for_pi(pi_id: int, data: CameraCreate = Body(...), db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi: raise HTTPException(404)
    cam = Camera(**data.dict(), orange_pi_id=pi_id); db.add(cam); db.commit(); db.refresh(cam)
    return cam

@app.get("/api/orangepi/{pi_id}/cameras", response_model=List[CameraOut])
def list_cameras_for_pi(pi_id: int, db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
    if not pi: raise HTTPException(404)
    return pi.cameras

@app.patch("/api/cameras/{camera_id}", response_model=CameraOut)
def patch_camera(camera_id: int, data: CameraUpdate = Body(...), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam: raise HTTPException(404)
    for key, value in data.dict(exclude_unset=True).items(): setattr(cam, key, value)
    db.commit(); db.refresh(cam); return cam

@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam: raise HTTPException(404)
    db.delete(cam); db.commit(); return {"status": "deleted"}

@app.get("/api/agent/versions")
def list_agent_versions():
    versions = []
    if os.path.isdir(AGENT_VERSIONS_DIR):
        for fname in sorted(os.listdir(AGENT_VERSIONS_DIR)):
            if fname.startswith("agent_v") and fname.endswith(".py"):
                versions.append({"version": fname[len("agent_v"):-len(".py")], "filename": fname})
    return {"versions": versions}

@app.get("/api/agent/{version}")
def get_agent_file(version: str):
    fname = f"agent_v{version}.py"; fpath = os.path.join(AGENT_VERSIONS_DIR, fname)
    if not os.path.exists(fpath): raise HTTPException(404)
    return FileResponse(fpath, media_type="text/plain", filename=fname)

@app.post("/api/agent/update/{device_id}")
def trigger_agent_update(device_id: int, version: str = Body(..., embed=True), db: Session = Depends(get_db)):
    pi = db.query(OrangePi).filter(OrangePi.id == device_id).first()
    if not pi: raise HTTPException(404)
    fpath = os.path.join(AGENT_VERSIONS_DIR, f"agent_v{version}.py")
    if not os.path.exists(fpath): raise HTTPException(404)
    cmd = Command(device_id=device_id, command="update", params=json.dumps({"version": version}))
    db.add(cmd); db.commit(); return {"status": "queued"}

@app.post("/api/scan_results")
def save_scan_results(device_id: int = Body(...), results: list = Body(...), db: Session = Depends(get_db)):
    for res in results: db.add(ScanResult(device_id=device_id, ip_address=res.get("ip"), rtsp_url=res.get("rtsp_url")))
    db.commit(); return {"status": "ok"}

@app.get("/api/orangepi/{device_id}/scan_results")
def get_scan_results(device_id: int, db: Session = Depends(get_db)):
    return [{"id": r.id, "ip": r.ip_address, "rtsp_url": r.rtsp_url} for r in db.query(ScanResult).filter(ScanResult.device_id == device_id, ScanResult.added == False).all()]

@app.post("/api/upload/{camera_id}")
async def upload_photo(camera_id: int, file: UploadFile = File(...), motion_level: int = Form(0), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id, Camera.enabled == True).first()
    if not cam: raise HTTPException(404)
    filename = f"cam{camera_id}_{uuid.uuid4().hex[:8]}.jpg"; filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f: shutil.copyfileobj(file.file, f)
    shot = Screenshot(camera_id=camera_id, filename=filename, original_path=filepath, resized_path=filepath, motion_level=motion_level)
    db.add(shot); db.commit(); return {"status": "ok", "filename": filename}

@app.get("/api/screenshots")
def list_screenshots(camera_id: Optional[int] = None, device_id: Optional[int] = None, page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    query = db.query(Screenshot)
    if camera_id is not None: query = query.filter(Screenshot.camera_id == camera_id)
    if device_id is not None: query = query.join(Camera).filter(Camera.orange_pi_id == device_id)
    total = query.count(); items = query.order_by(Screenshot.created_at.desc()).offset((page-1)*limit).limit(limit).all()
    return {"items": [{"id": s.id, "filename": s.filename, "url": f"/uploads/resized/{s.filename}", "description": s.description, "created_at": s.created_at.isoformat()} for s in items], "total": total}

@app.post("/api/generate_report/{device_id}")
def generate_report(device_id: int, db: Session = Depends(get_db)):
    now = datetime.utcnow(); start_time = now - timedelta(hours=12)
    pis = db.query(OrangePi).filter(OrangePi.id == device_id).first()
    if not pis: raise HTTPException(404)
    for camera in pis.cameras:
        screenshots = db.query(Screenshot).filter(Screenshot.camera_id == camera.id, Screenshot.created_at >= start_time).all()
        if not screenshots: continue
        descriptions = [f"[{s.created_at.strftime('%H:%M')}] {s.description}" for s in screenshots if s.description]
        if not descriptions: continue
        prompt = camera.report_prompt or "Сделай краткий отчёт по событиям за последние 12 часов"
        model = camera.report_model or "qwen2.5vl:3b"
        full_prompt = f"{prompt}\n\nСобытия:\n" + "\n".join(descriptions)
        try:
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            resp = requests.post(f"{ollama_base}/api/generate", json={"model": model, "prompt": full_prompt, "stream": False}, timeout=60)
            if resp.status_code == 200:
                report_text = resp.json().get("response", "").strip()
                if report_text:
                    report = Report(device_id=device_id, camera_id=camera.id, start_time=start_time, end_time=now, report_text=report_text)
                    db.add(report); db.commit()
        except: pass
    return {"status": "ok"}

@app.get("/api/reports")
def list_reports(device_id: Optional[int] = None, limit: int = 10, db: Session = Depends(get_db)):
    query = db.query(Report).order_by(Report.created_at.desc())
    if device_id is not None: query = query.filter(Report.device_id == device_id)
    return [{"id": r.id, "device_id": r.device_id, "start_time": r.start_time.isoformat(), "end_time": r.end_time.isoformat(), "report_text": r.report_text, "created_at": r.created_at.isoformat()} for r in query.limit(limit).all()]

@app.get("/")
def root(): return FileResponse("/app/static/index.html")
@app.get("/device/{pi_id}")
def device_page(pi_id: int): return FileResponse("/app/static/device.html")
app.mount("/uploads/resized", StaticFiles(directory=UPLOAD_DIR), name="uploads_resized")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")
