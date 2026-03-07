import os
import hashlib
import threading
import json
import io
import datetime
import opencc
import xml.etree.ElementTree as ET
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
WATCH_PATH = "/data"
VERSION = "1.5.8"
# Secure API key from environment variable
API_KEY = os.getenv("API_KEY", "DEFAULT_SECURE_KEY")

# Translation mode configuration
TRANS_MODE = os.getenv("TRANS_MODE", "s2t").lower()
CONFIG_FILE = "s2t.json" if TRANS_MODE == "s2t" else "t2s.json"

# --- GLOBAL STATE ---
is_running = False
stop_event = threading.Event()
status_message = "System Ready"
log_history = []
translated_count = 0 

# --- DATABASE SETUP ---
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    path = Column(String, primary_key=True)
    hash = Column(String)
    last_processed = Column(DateTime, default=func.now())

# Create tables if they do not exist
Base.metadata.create_all(bind=engine)
converter = opencc.OpenCC(CONFIG_FILE)
app = FastAPI()

# --- API MODELS ---
class TriggerRequest(BaseModel):
    key: str

# --- NFO PROCESSING LOGIC ---
TARGET_TAGS = ['outline', 'title', 'plot', 'tag', 'genre', 'series']

def process_nfo(file_path):
    """Parses and translates specific XML tags within .nfo files."""
    global translated_count
    if not file_path.lower().endswith(".nfo"): 
        return
        
    db = SessionLocal()
    try:
        with open(file_path, "rb") as f:
            curr_hash = hashlib.md5(f.read()).hexdigest()
            
        # Skip if file hasn't changed
        rec = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if rec and rec.hash == curr_hash: 
            return 
        
        parser = ET.XMLParser(encoding="utf-8")
        tree = ET.parse(file_path, parser=parser)
        root = tree.getroot()
        
        modified = False
        for tag_name in TARGET_TAGS:
            for element in root.findall(f".//{tag_name}"):
                if element.text:
                    translated = converter.convert(element.text)
                    if translated != element.text:
                        element.text = translated
                        modified = True
                        
        if modified:
            tree.write(file_path, encoding="utf-8", xml_declaration=True)
            with open(file_path, "rb") as f:
                new_h = hashlib.md5(f.read()).hexdigest()
            
            if rec:
                rec.hash = new_h
                rec.last_processed = datetime.datetime.now()
            else:
                db.add(FileRecord(path=file_path, hash=new_h, last_processed=datetime.datetime.now()))
            
            db.commit()
            translated_count += 1
            log_history.insert(0, f"✅ Updated: {os.path.basename(file_path)}")
        elif not rec:
            # Mark clean file as processed to skip in next scan
            db.add(FileRecord(path=file_path, hash=curr_hash, last_processed=datetime.datetime.now()))
            db.commit()
            
    except Exception as e:
        db.rollback()
        log_history.insert(0, f"❌ Error in {os.path.basename(file_path)}: {str(e)}")
    finally:
        db.close()

def manual_monitor_task(source="Manual"):
    """Background thread task to walk directory and process files."""
    global is_running, status_message, translated_count, log_history
    is_running = True
    stop_event.clear()
    translated_count = 0
    now = datetime.datetime.now().strftime("%H:%M:%S")
    
    log_history.insert(0, f"🚀 [{now}] Starting Scan (Source: {source})...")
    status_message = f"Scanning ({source})..."
    
    try:
        for root, _, files in os.walk(WATCH_PATH):
            for file in files:
                if stop_event.is_set():
                    log_history.insert(0, f"🛑 [{datetime.datetime.now().strftime('%H:%M:%S')}] Task Stopped.")
                    status_message = "Stopped"
                    is_running = False
                    return
                process_nfo(os.path.join(root, file))
                
        status_message = f"Scan Complete ({datetime.datetime.now().strftime('%H:%M:%S')})"
        log_history.insert(0, f"🏁 Finished scanning all files.")
    finally:
        is_running = False

# --- WEB UI ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard with smart auto-refresh logic."""
    db = SessionLocal()
    total_db_records = db.query(FileRecord).count()
    db.close()

    # Smart Auto-Renew: refreshes every 3s ONLY when a task is running
    refresh_tag = '<meta http-equiv="refresh" content="3">' if is_running else ""
    
    # Dynamic status badge colors
    status_color = "#ffc107" if is_running else "#28a745"
    if "Stopped" in status_message: status_color = "#dc3545"
    
    log_content = "\n".join(log_history)

    return f"""
    <html>
        <head>
            {refresh_tag}
            <title>NFO Monitor v{VERSION}</title>
            <style>
                body {{ font-family: sans-serif; padding: 20px; background: #f4f7f9; text-align: center; }}
                .card {{ max-width: 480px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: left; }}
                .status-badge {{ float: right; padding: 4px 10px; border-radius: 20px; background: {status_color}; color: white; font-size: 11px; font-weight: bold; }}
                .stats-box {{ display: flex; justify-content: space-around; background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #dee2e6; }}
                .stat-num {{ display: block; font-size: 24px; font-weight: bold; color: #333; text-align: center; }}
                .log-window {{ 
                    background: #1e1e1e; color: #33ff33; padding: 12px; height: 200px; 
                    overflow-y: scroll; border-radius: 6px; font-family: monospace; 
                    font-size: 11px; white-space: pre-wrap; word-wrap: break-word;
                }}
                .btn {{ 
                    width: 100%; height: 40px; margin: 5px 0; border: none; 
                    border-radius: 6px; cursor: pointer; font-weight: bold; color: white; 
                    text-decoration: none; display: flex; align-items: center; justify-content: center; 
                    font-size: 13px; box-sizing: border-box;
                }}
                .btn-start {{ background: #28a745; }} .btn-stop {{ background: #dc3545; }} .btn-db {{ background: #17a2b8; }}
                button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
                .db-grid {{ display: flex; gap: 10px; margin-top: 10px; }}
                .db-grid > * {{ flex: 1; }}
            </style>
        </head>
        <body>
            <div class="card">
                <span class="status-badge">{status_message}</span>
                <h2 style="margin-top:0;">NFO Monitor <small style="color:#999; font-size:12px;">v{VERSION}</small></h2>
                
                <div class="stats-box">
                    <div><span class="stat-num" style="color:#28a745;">{translated_count}</span><small>Updated Now</small></div>
                    <div><span class="stat-num" style="color:#007bff;">{total_db_records}</span><small>Total Records</small></div>
                </div>

                <div class="log-window">{log_content if log_history else "Ready to scan..."}</div>

                <hr style="border:0; border-top:1px solid #eee; margin:20px 0;">
                
                <form action="/start" method="post"><button type="submit" class="btn btn-start" {"disabled" if is_running else ""}>▶ START MONITOR TASK</button></form>
                <form action="/stop" method="post"><button type="submit" class="btn btn-stop" {"disabled" if not is_running else ""}>⏹ STOP TASK</button></form>
                
                <div class="db-grid">
                    <a href="/export" class="btn btn-db">📤 EXPORT DB</a>
                    <form action="/import" method="post" enctype="multipart/form-data">
                        <input type="file" name="file" id="f" hidden onchange="this.form.submit()">
                        <button type="button" class="btn btn-db" onclick="document.getElementById('f').click()">📥 IMPORT DB</button>
                    </form>
                </div>
            </div>
        </body>
    </html>
    """

@app.post("/start")
async def start_task():
    global is_running
    if not is_running:
        threading.Thread(target=manual_monitor_task, args=("Manual UI",), daemon=True).start()
    return RedirectResponse(url="/", status_code=303)

@app.post("/stop")
async def stop_task():
    stop_event.set()
    return RedirectResponse(url="/", status_code=303)

# --- API & BACKUP ENDPOINTS ---

@app.post("/trigger")
async def trigger_task(data: TriggerRequest):
    """External trigger for automation tools (e.g., qBittorrent, Sonarr)."""
    global is_running, status_message
    try:
        if data.key != API_KEY:
            return JSONResponse(status_code=403, content={"status": "error", "message": "Invalid API Key"})
        
        if is_running:
            return {"status": "ok", "message": "Task already in progress"}
        
        status_message = "API Trigger Received..."
        threading.Thread(target=manual_monitor_task, args=("API POST",), daemon=True).start()
        return {"status": "ok", "message": "Background scan started successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Server Error: {str(e)}"})

@app.get("/export")
async def export_db():
    """Exports processed file database to JSON file."""
    db = SessionLocal()
    try:
        recs = db.query(FileRecord).all()
        data = [{"path": r.path, "hash": r.hash, "last_processed": r.last_processed.isoformat()} for r in recs]
        return StreamingResponse(
            io.BytesIO(json.dumps(data, indent=4).encode("utf-8")), 
            media_type="application/json", 
            headers={"Content-Disposition": "attachment; filename=nfo_backup.json"}
        )
    finally:
        db.close()

@app.post("/import")
async def import_db(file: UploadFile = File(...)):
    """Imports and merges records from a JSON backup file."""
    contents = await file.read()
    data = json.loads(contents)
    db = SessionLocal()
    try:
        for item in data:
            rec = db.query(FileRecord).filter(FileRecord.path == item["path"]).first()
            if rec:
                rec.hash = item["hash"]
            else:
                db.add(FileRecord(path=item["path"], hash=item["hash"], last_processed=datetime.datetime.fromisoformat(item["last_processed"])))
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)