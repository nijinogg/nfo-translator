import os
import time
import hashlib
import threading
import json
import io
import datetime
import opencc
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
WATCH_PATH = "/data"
VERSION = "1.2.8"

TRANS_MODE = os.getenv("TRANS_MODE", "s2t").lower()
CONFIG_FILE = "s2t.json" if TRANS_MODE == "s2t" else "t2s.json"
MODE_DESC = "Simplified → Traditional" if TRANS_MODE == "s2t" else "Traditional → Simplified"

try:
    STARTUP_DELAY = int(os.getenv("STARTUP_DELAY", "0"))
except (ValueError, TypeError):
    STARTUP_DELAY = 0

SCANNING_ACTIVE = False
APP_BOOT_TIME = time.time()

# --- DATABASE SETUP ---
engine = None
for i in range(15):
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        engine.connect()
        break
    except Exception:
        time.sleep(5)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    path = Column(String, primary_key=True)
    hash = Column(String)
    last_processed = Column(DateTime, default=func.now())

Base.metadata.create_all(bind=engine)
converter = opencc.OpenCC(CONFIG_FILE)
app = FastAPI()

# --- TRANSLATION LOGIC ---
TARGET_TAGS = ['outline', 'title', 'plot', 'tag', 'genre', 'series']

def process_nfo(file_path):
    if not file_path.lower().endswith(".nfo"):
        return
    db = SessionLocal()
    try:
        with open(file_path, "rb") as f:
            curr_hash = hashlib.md5(f.read()).hexdigest()
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
        elif not rec:
            db.add(FileRecord(path=file_path, hash=curr_hash, last_processed=datetime.datetime.now()))
            db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()

# --- WATCHER ---
def run_full_scan():
    for root, _, files in os.walk(WATCH_PATH):
        for file in files: process_nfo(os.path.join(root, file))

class NFOHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory: process_nfo(event.src_path)
    def on_created(self, event):
        if not event.is_directory: process_nfo(event.src_path)

def boot_sequence():
    global SCANNING_ACTIVE
    if STARTUP_DELAY > 0: time.sleep(STARTUP_DELAY)
    SCANNING_ACTIVE = True
    obs = Observer(); obs.schedule(NFOHandler(), WATCH_PATH, recursive=True); obs.start()
    run_full_scan()

threading.Thread(target=boot_sequence, daemon=True).start()

# --- DASHBOARD UI (REVERTED TO v1.2.1 STYLE) ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(20).all()
    total = db.query(FileRecord).count()
    db.close()
    
    elapsed = time.time() - APP_BOOT_TIME
    remaining = int(max(0, STARTUP_DELAY - elapsed))
    is_active = SCANNING_ACTIVE or remaining <= 0
    status_text = "Active" if is_active else f"Waiting ({remaining}s)"
    status_color = "#28a745" if is_active else "#ffc107"
    refresh = '<meta http-equiv="refresh" content="5">'

    return f"""
    <html>
        <head>
            {refresh}
            <title>NFO Pro v{VERSION}</title>
            <style>
                body {{ font-family: sans-serif; padding: 20px; background: #f4f7f9; }}
                .card {{ max-width: 900px; margin: auto; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .status-badge {{ padding: 5px 12px; border-radius: 20px; background: {status_color}; color: white; font-weight: bold; }}
                .nav {{ display: flex; gap: 10px; margin: 20px 0; background: #eee; padding: 15px; border-radius: 8px; align-items: center; }}
                .btn {{ height: 36px; display: inline-flex; align-items: center; padding: 0 15px; border-radius: 6px; border: none; cursor: pointer; color: white; text-decoration: none; font-size: 13px; }}
                .btn-scan {{ background: #28a745; }} .btn-export {{ background: #17a2b8; }} .btn-import {{ background: #6c757d; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 10px; border-bottom: 1px solid #ddd; text-align: left; font-size: 13px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h1>NFO Monitor <small style="font-size:0.4em; color:#999;">v{VERSION}</small></h1>
                    <span class="status-badge">{status_text}</span>
                </div>
                <p>Latest 20 / Total: {total} | <b>Mode: {MODE_DESC}</b></p>
                <div class="nav">
                    <form action="/rescan" method="post" style="margin:0;"><button class="btn btn-scan">🔄 Rescan</button></form>
                    <a href="/export" class="btn btn-export">📤 Export</a>
                    <div style="margin-left:auto; display:flex; align-items:center; gap:10px;">
                        <form action="/import" method="post" enctype="multipart/form-data" style="margin:0; display:flex; gap:5px;">
                            <input type="file" name="file" accept=".json" required>
                            <button type="submit" class="btn btn-import">📥 Import</button>
                        </form>
                    </div>
                </div>
                <table>
                    <thead><tr><th>Processed</th><th>Path</th></tr></thead>
                    <tbody>
                        {"".join([f"<tr><td>{r.last_processed.strftime('%H:%M:%S')}</td><td>{r.path}</td></tr>" for r in records])}
                    </tbody>
                </table>
            </div>
        </body>
    </html>
    """

@app.get("/export")
async def export_db():
    db = SessionLocal()
    try:
        recs = db.query(FileRecord).all()
        data = [{"path": r.path, "hash": r.hash, "last_processed": r.last_processed.isoformat()} for r in recs]
        # Keep the JSON fix from v1.2.2 (indented and UTF-8)
        json_str = json.dumps(data, indent=4, ensure_ascii=False)
        return StreamingResponse(io.BytesIO(json_str.encode("utf-8")), media_type="application/json", headers={"Content-Disposition": "attachment; filename=backup.json"})
    finally:
        db.close()

@app.post("/import")
async def import_db(file: UploadFile = File(...)):
    contents = await file.read(); data = json.loads(contents); db = SessionLocal()
    try:
        for item in data:
            rec = db.query(FileRecord).filter(FileRecord.path == item["path"]).first()
            if rec: rec.hash = item["hash"]
            else: db.add(FileRecord(path=item["path"], hash=item["hash"], last_processed=datetime.datetime.fromisoformat(item["last_processed"])))
        db.commit()
    finally: db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/rescan")
async def rescan(bg: BackgroundTasks):
    bg.add_task(run_full_scan)
    return RedirectResponse(url="/", status_code=303)