import requests, psutil, time, os, cv2, numpy as np
from datetime import datetime

SERVER_URL = "https://camera.cloudpub.ru"
DEVICE_ID = 1
API_KEY = "default_key"

def get_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return float(f.read().strip()) / 1000.0
    except:
        return 0.0

def send_status():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    temp = get_temperature()
    payload = {"cpu_usage": cpu, "ram_usage": ram, "disk_usage": disk, "temperature": temp}
    try:
        resp = requests.post(f"{SERVER_URL}/api/orangepi/{DEVICE_ID}/status", json=payload, headers={"X-API-Key": API_KEY}, timeout=10)
        print(f"[{datetime.now()}] Status sent, response: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[{datetime.now()}] Status error: {e}", flush=True)

def get_cameras():
    try:
        resp = requests.get(f"{SERVER_URL}/api/orangepi/{DEVICE_ID}/cameras")
        if resp.status_code == 200: return resp.json()
        else: print(f"Error getting cameras: {resp.status_code}", flush=True); return []
    except Exception as e: print(f"Exception getting cameras: {e}", flush=True); return []

def get_pending_commands():
    try:
        resp = requests.get(f"{SERVER_URL}/api/orangepi/{DEVICE_ID}/commands")
        if resp.status_code == 200: return resp.json()
        else: print(f"Error getting commands: {resp.status_code}", flush=True); return []
    except Exception as e: print(f"Exception getting commands: {e}", flush=True); return []

def complete_command(command_id):
    try:
        resp = requests.put(f"{SERVER_URL}/api/commands/{command_id}/complete")
        if resp.status_code == 200: print(f"Command {command_id} completed", flush=True); return True
        else: print(f"Error completing command {command_id}: {resp.status_code}", flush=True); return False
    except Exception as e: print(f"Exception completing command {command_id}: {e}", flush=True); return False

def detect_motion(prev_frame, curr_frame, sensitivity=50):
    MIN_CHANGED_PIXELS = 50
    if prev_frame is None or curr_frame is None: return False
    prev_gray = cv2.GaussianBlur(cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    curr_gray = cv2.GaussianBlur(cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    frame_delta = cv2.absdiff(prev_gray, curr_gray)
    thresh = cv2.threshold(frame_delta, 20, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_changed_pixels = sum(cv2.contourArea(c) for c in contours)
    total_pixels = thresh.size
    motion_percent = (total_changed_pixels / total_pixels) * 100.0
    threshold = 0.1 * (50.0 / max(1, sensitivity))
    print(f"Motion: changed={motion_percent:.4f}% (contours={len(contours)}), threshold={threshold:.4f}%", flush=True)
    return motion_percent > threshold and total_changed_pixels > MIN_CHANGED_PIXELS

def do_snapshot(camera, motion_level=0):
    rtsp = camera.get('rtsp_url')
    if not rtsp: return False
    cap = cv2.VideoCapture(rtsp)
    if not cap.isOpened():
        print(f"Camera {camera['id']}: cannot open RTSP stream", flush=True)
        return False
    ret, frame = cap.read()
    cap.release()
    if not ret: return False
    height = camera.get('screenshot_quality', 320)
    width = int(frame.shape[1] * (height / frame.shape[0]))
    resized = cv2.resize(frame, (width, height))
    filename = f"/tmp/capture_{camera['id']}_{int(time.time())}.jpg"
    cv2.imwrite(filename, resized)
    try:
        with open(filename, 'rb') as f:
            files = {'file': f}; data = {'motion_level': motion_level}
            resp = requests.post(f"{SERVER_URL}/api/upload/{camera['id']}", files=files, data=data, headers={"X-API-Key": API_KEY}, timeout=15)
            print(f"Camera {camera['id']}: snapshot sent, response: {resp.status_code}", flush=True)
            return resp.status_code == 200
    except Exception as e:
        print(f"Camera {camera['id']}: upload error: {e}", flush=True)
        return False
    finally:
        if os.path.exists(filename): os.remove(filename)

def process_commands(cameras_dict):
    commands = get_pending_commands()
    print(f"Got commands: {len(commands)}", flush=True)
    for cmd in commands:
        cam = cameras_dict.get(cmd['camera_id'])
        if not cam:
            print(f"Camera {cmd['camera_id']} not found for command {cmd['id']}", flush=True)
            complete_command(cmd['id'])
            continue
        print(f"Executing command {cmd['command']} for camera {cam['name']}", flush=True)
        if do_snapshot(cam, motion_level=0): complete_command(cmd['id'])

def motion_detection_loop(cameras):
    if not cameras: return
    for cam in cameras:
        rtsp = cam.get('rtsp_url')
        if not rtsp: continue
        cap = cv2.VideoCapture(rtsp)
        if not cap.isOpened():
            print(f"Camera {cam['id']}: cannot open RTSP stream", flush=True)
            continue
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            continue
        interval = cam.get('detection_interval', 30)
        print(f"Camera {cam['id']}: waiting {interval}s for second frame...", flush=True)
        time.sleep(interval)
        ret, curr_frame = cap.read()
        cap.release()
        if not ret: continue
        sensitivity = cam.get('sensitivity', 50)
        if detect_motion(prev_frame, curr_frame, sensitivity):
            print(f"Motion detected on camera {cam['id']}!", flush=True)
            do_snapshot(cam, motion_level=100)
        else:
            print(f"Camera {cam['id']}: no motion detected", flush=True)

def main():
    while True:
        try:
            send_status()
            cameras = get_cameras()
            cameras_dict = {c['id']: c for c in cameras}
            process_commands(cameras_dict)
            motion_detection_loop(cameras)
        except Exception as e:
            print(f"Unexpected error in main loop: {e}", flush=True)
        time.sleep(30)

if __name__ == "__main__":
    main()
