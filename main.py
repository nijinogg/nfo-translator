import os
import time
import hashlib
import threading
import json
import io
import opencc
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
WATCH_PATH = "/data"
STARTUP_DELAY = int(os.getenv("STARTUP_DELAY", "0"))

# Global flag to track if scanning logic is running
SCANNING_ACTIVE = False

# --- DATABASE SETUP ---
engine = None
for i in range(15):
    try:
        engine = create_engine(DATABASE_URL)
        engine.connect()
        print("✅ Connected to PostgreSQL.")
        break
    except Exception as e:
        print(f"⏳ Waiting for database ({i+1}/15)...")
        time.sleep(5)

if not engine:
    raise Exception("❌ Could not connect to database.")

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    path = Column(String, primary_key=True)
    hash = Column(String)
    last_processed = Column(DateTime, default=func.now(), onupdate=func.now())

Base.metadata.create_all(bind=engine)

# Official OpenCC initialization (Simplified to Traditional)
converter = opencc.OpenCC('s2t.json')
app = FastAPI()

# --- CORE LOGIC ---
def process_nfo(file_path):
    if not file_path.lower().endswith(".nfo"):
        return

    db = SessionLocal()
    try:
        with open(file_path, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        record = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if record and record.hash == current_hash:
            return 

        print(f"📝 Translating: {file_path}")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        traditional_content = converter.convert(content)

        with open(file_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(traditional_content)

        with open(file_path, "rb") as f:
            new_hash = hashlib.md5(f.read()).hexdigest()

        if record:
            record.hash = new_hash
        else:
            db.add(FileRecord(path=file_path, hash=new_hash))
        
        db.commit()
    except Exception as e:
        print(f"❌ Error on {file_path}: {e}")
    finally:
        db.close()

def run_full_scan():
    print("🚀 Starting full recursive scan...")
    for root, _, files in os.walk(WATCH_PATH):
        for file in files:
            process_nfo(os.path.join(root, file))
    print("🏁 Full scan complete.")

# --- WATCHER ---
class SubfolderHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory: process_nfo(event.src_path)
    def on_created(self, event):
        if not event.is_directory: process_nfo(event.src_path)

def start_watcher():
    observer = Observer()
    observer.schedule(SubfolderHandler(), WATCH_PATH, recursive=True)
    observer.start()
    try:
        while True: time.sleep(1)
    except:
        observer.stop()

# --- STARTUP HANDLER ---
def boot_sequence():
    global SCANNING_ACTIVE
    if STARTUP_DELAY > 0:
        print(f"🕒 Startup delay: {STARTUP_DELAY}s. Use this time to IMPORT backup.")
        time.sleep(STARTUP_DELAY)
    
    SCANNING_ACTIVE = True
    threading.Thread(target=start_watcher, daemon=True).start()
    threading.Thread(target=run_full_scan, daemon=True).start()

threading.Thread(target=boot_sequence, daemon=True).start()

# --- WEB UI ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    # Updated to show only the latest 20 rows
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(20).all()
    total = db.query(FileRecord).count()
    db.close()
    
    current_status = "Active" if SCANNING_ACTIVE else "Waiting (Delay Mode)"
    status_color = "#28a745" if SCANNING_ACTIVE else "#ffc107"
    refresh_tag = '<meta http-equiv="refresh" content="5">' if not SCANNING_ACTIVE else ""
    
    html = f"""
    <html>
        <head>
            {refresh_tag}
            <title>NFO Pro Translator</title>
            <style>
                body {{ font-family: -apple-system, sans-serif; padding: 30px; background: #f4f7f9; color: #333; }}
                .card {{ max-width: 1000px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }}
                .status-badge {{ 
                    padding: 4px 12px; border-radius: 20px; font-size: 0.85em; 
                    background: {status_color}; color: white; font-weight: bold;
                }}
                .nav {{ 
                    display: flex; gap: 15px; margin: 25px 0; background: #f8f9fa; 
                    padding: 15px; border-radius: 8px; align-items: center; 
                }}
                .btn {{ 
                    height: 38px; display: inline-flex; align-items: center; justify-content: center;
                    padding: 0 18px; border-radius: 6px; border: none; cursor: pointer; 
                    color: white; text-decoration: none; font-weight: 500; font-size: 13px; 
                }}
                .btn-scan {{ background: #28a745; }} 
                .btn-export {{ background: #17a2b8; }} 
                .btn-import {{ background: #6c757d; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th, td {{ padding: 12px; border-bottom: 1px solid #eee; text-align: left; font-size: 13px; }}
                th {{ background: #f1f3f5; color: #495057; text-transform: uppercase; font-size: 11px; }}
                .file-path {{ color: #007bff; word-break: break-all; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h1>NFO Monitor</h1>
                    <span class="status-badge">{current_status}</span>
                </div>
                <p>Showing latest 20 / Total: <strong>{total}</strong></p>

                <div class="nav">
                    <form action="/rescan" method="post" style="margin:0;"><button class="btn btn-scan" type="submit">🔄 Rescan All</button></form>
                    <a href="/export" class="btn btn-export">📤 Export Backup</a>
                    
                    <div style="margin-left:auto; display:flex; align-items:center; gap:10px; border-left:1px solid #ddd; padding-left:15px;">
                        <form action="/import" method="post" enctype="multipart/form-data" style="margin:0; display:flex; align-items:center; gap:10px;">
                            <input type="file" name="file" accept=".json" required style="font-size:12px;">
                            <button type="submit" class="btn btn-import">📥 Import JSON</button>
                        </form>
                    </div>
                </div>

                <table>
                    <thead>
                        <tr><th>Path</th><th>Processed (Local Time)</th></tr>
                    </thead>
                    <tbody>
                        {"".join([f"<tr><td class='file-path'>{r.path}</td><td>{r.last_processed.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>" for r in records])}
                    </tbody>
                </table>
            </div>
        </body>
    </html>
    """
    return html

@app.post("/rescan")
async def trigger_rescan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_full_scan)
    return RedirectResponse(url="/", status_code=303)

@app.get("/export")
async def export_db():
    db = SessionLocal()
    records = db.query(FileRecord).all()
    db.close()
    data = [{"path": r.path, "hash": r.hash, "last_processed": r.last_processed.isoformat()} for r in records]
    return StreamingResponse(
        io.BytesIO(json.dumps(data, indent=2).encode()), 
        media_type="application/json", 
        headers={"Content-Disposition": "attachment; filename=nfo_backup.json"}
    )

@app.post("/import")
async def import_db(file: UploadFile = File(...)):
    contents = await file.read()
    data = json.loads(contents)
    db = SessionLocal()
    try:
        for item in data:
            record = db.query(FileRecord).filter(FileRecord.path == item["path"]).first()
            if record: record.hash = item["hash"]
            else: db.add(FileRecord(path=item["path"], hash=item["hash"]))
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)