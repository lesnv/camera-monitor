#!/usr/bin/env python3
"""Добавляет недостающие API эндпоинты в main.py"""

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Проверяем, не добавлены ли уже эндпоинты
if '@app.get("/api/orangepi/{pi_id}")' in content:
    print("ℹ️ Эндпоинты уже есть в main.py")
else:
    # Код новых эндпоинтов
    new_code = '''
# === ДОБАВЛЕНО: Недостающие эндпоинты ===

# Orange Pi by ID
@app.get("/api/orangepi/{pi_id}")
def get_orangepi(pi_id: int):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        return pi
    finally:
        db.close()

@app.put("/api/orangepi/{pi_id}")
def update_orangepi(pi_id: int, data: OrangePiCreate):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        pi.name = data.name
        pi.ip = data.ip
        db.commit()
        db.refresh(pi)
        return pi
    finally:
        db.close()

# Камеры для Orange Pi
@app.post("/api/orangepi/{pi_id}/cameras")
def create_camera_for_pi(pi_id: int, data: CameraCreate):
    db = SessionLocal()
    try:
        pi = db.query(OrangePi).filter(OrangePi.id == pi_id).first()
        if not pi:
            raise HTTPException(404, "Orange Pi not found")
        cam = Camera(**data.dict(), orange_pi_id=pi_id)
        db.add(cam)
        db.commit()
        db.refresh(cam)
        return cam
    finally:
        db.close()

# Screenshots list
@app.get("/api/screenshots")
def list_screenshots(date: str = None, page: int = 1, limit: int = 20):
    db = SessionLocal()
    try:
        query = db.query(Screenshot)
        if date:
            query = query.filter(Screenshot.created_at >= date)
        items = query.order_by(Screenshot.created_at.desc()).offset((page-1)*limit).limit(limit).all()
        total = query.count()
        return {"items": [{"id": s.id, "filename": s.filename, "url": f"/uploads/resized/{s.filename}", "created_at": s.created_at, "motion_level": s.motion_level} for s in items], "total": total, "page": page, "total_pages": (total + limit - 1) // limit}
    finally:
        db.close()

# Static file handler for device pages
from starlette.responses import FileResponse
import os

@app.get("/device/{pi_id}/cameras.html")
async def device_cameras_html(pi_id: int):
    path = "/app/static/device/cameras.html"
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404, "File not found")

'''
    
    # Вставляем перед if __name__
    if 'if __name__ == "__main__":' in content:
        content = content.replace('if __name__ == "__main__":', new_code + '\nif __name__ == "__main__":')
        with open('main.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Эндпоинты добавлены в main.py")
    else:
        print("❌ Не найдено 'if __name__' в main.py")
