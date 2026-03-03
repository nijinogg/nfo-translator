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

# Official OpenCC initialization (s2t.json for Simplified to Traditional)
converter = opencc.OpenCC('s2t.json')
app = FastAPI()

# --- CORE LOGIC ---
def process_nfo(file_path):
    if not file_path.lower().endswith(".nfo"):
        return

    db = SessionLocal()
    try:
        # Calculate current hash
        with open(file_path, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        # Check DB
        record = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if record and record.hash == current_hash:
            return 

        print(f"📝 Translating: {file_path}")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        traditional_content = converter.convert(content)

        with open(file_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(traditional_content)

        # Update record
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
    print("🚀 Starting full scan...")
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
    if STARTUP_DELAY > 0:
        print(f"🕒 Startup delay: {STARTUP_DELAY}s. Use this time to IMPORT backup.")
        time.sleep(STARTUP_DELAY)
    
    threading.Thread(target=start_watcher, daemon=True).start()
    threading.Thread(target=run_full_scan, daemon=True).start()

threading.Thread(target=boot_sequence, daemon=True).start()

# --- WEB UI ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(100).all()
    total = db.query(FileRecord).count()
    db.close()
    
    html = f"""
    <html>
        <head><title>NFO Pro</title><style>
            body {{ font-family: sans-serif; padding: 30px; background: #f4f7f9; }}
            .card {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .nav {{ display: flex; gap: 10px; margin: 20px 0; background: #eee; padding: 15px; border-radius: 8px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #ddd; text-align: left; font-size: 13px; }}
            th {{ background: #007bff; color: white; }}
            .btn {{ padding: 10px 15px; border-radius: 5px; border: none; cursor: pointer; color: white; text-decoration: none; }}
            .btn-scan {{ background: #28a745; }} .btn-export {{ background: #17a2b8; }} .btn-import {{ background: #6c757d; }}
        </style></head>
        <body>
            <div class="card">
                <h1>NFO Translator Dashboard</h1>
                <p>Status: <strong>{"Waiting (Delay Mode)" if STARTUP_DELAY > 0 else "Active"}</strong> | Total Files: <strong>{total}</strong></p>
                <div class="nav">
                    <form action="/rescan" method="post"><button class="btn btn-scan">🔄 Force Rescan</button></form>
                    <a href="/export" class="btn btn-export">📤 Export Backup</a>
                    <form action="/import" method="post" enctype="multipart/form-data" style="margin-left:auto;">
                        <input type="file" name="file" accept=".json" required>
                        <button type="submit" class="btn btn-import">📥 Import Backup</button>
                    </form>
                </div>
                <table>
                    <tr><th>File Path</th><th>Processed Time</th></tr>
                    {"".join([f"<tr><td>{r.path}</td><td>{r.last_processed}</td></tr>" for r in records])}
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
    return StreamingResponse(io.BytesIO(json.dumps(data).encode()), media_type="application/json", 
                             headers={"Content-Disposition": "attachment; filename=nfo_backup.json"})

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