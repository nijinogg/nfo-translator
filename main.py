import os, time, hashlib, threading
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import opencc
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- DATABASE & CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    path = Column(String, primary_key=True)
    hash = Column(String)
    last_processed = Column(DateTime, default=func.now(), onupdate=func.now())

Base.metadata.create_all(bind=engine)
converter = opencc.OpenCC('s2t')
app = FastAPI()

# --- CORE LOGIC ---
def process_nfo(file_path):
    if not file_path.lower().endswith(".nfo"): return
    db = SessionLocal()
    try:
        # 1. Calculate Hash
        with open(file_path, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        # 2. Check DB
        record = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if record and record.hash == current_hash:
            return # Already translated, skip

        # 3. Translate
        print(f"Processing: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            traditional = converter.convert(f.read())
        
        with open(file_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(traditional)

        # 4. Update DB with NEW hash
        with open(file_path, "rb") as f:
            new_hash = hashlib.md5(f.read()).hexdigest()

        if record: record.hash = new_hash
        else: db.add(FileRecord(path=file_path, hash=new_hash))
        db.commit()
    except Exception as e:
        print(f"Error on {file_path}: {e}")
    finally:
        db.close()

def run_full_scan():
    print("Scanning all subfolders in /data...")
    for root, dirs, files in os.walk("/data"):
        for file in files:
            process_nfo(os.path.join(root, file))
    print("Scan complete.")

# --- WATCHER ---
class SubfolderHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory: process_nfo(event.src_path)
    def on_created(self, event):
        if not event.is_directory: process_nfo(event.src_path)

def start_watcher():
    event_handler = SubfolderHandler()
    observer = Observer()
    # RECURSIVE=TRUE is the key for subfolders
    observer.schedule(event_handler, "/data", recursive=True)
    observer.start()
    try:
        while True: time.sleep(1)
    except: observer.stop()

# Start Watcher and Initial Scan on Boot
threading.Thread(target=start_watcher, daemon=True).start()
threading.Thread(target=run_full_scan, daemon=True).start()

# --- WEB UI ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(50).all()
    total = db.query(FileRecord).count()
    db.close()
    
    html = f"""
    <html>
        <head><title>NFO Monitor</title><style>
            body {{ font-family: sans-serif; padding: 20px; background: #f0f2f5; }}
            table {{ width: 100%; border-collapse: collapse; background: white; margin-top: 20px; }}
            th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; font-size: 14px; }}
            th {{ background: #007bff; color: white; }}
            .btn {{ padding: 10px 20px; background: #28a745; color: white; border: none; cursor: pointer; border-radius: 4px; text-decoration: none; }}
        </style></head>
        <body>
            <h1>NFO Translator Dashboard</h1>
            <p>Total Translated: <strong>{total}</strong></p>
            <form action="/rescan" method="post"><button class="btn" type="submit">🔄 Force Subfolder Rescan</button></form>
            <table>
                <tr><th>File Path (Subfolders included)</th><th>Processed Time</th></tr>
                {"".join([f"<tr><td>{r.path}</td><td>{r.last_processed}</td></tr>" for r in records])}
            </table>
        </body>
    </html>
    """
    return html

@app.post("/rescan")
async def trigger_rescan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_full_scan)
    return RedirectResponse(url="/", status_code=303)