import os, time, hashlib, threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import opencc
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# --- DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/nfo_monitor")
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

# --- WEB APP SETUP ---
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(100).all()
    total = db.query(FileRecord).count()
    db.close()
    
    # Simple HTML Template
    html_content = f"""
    <html>
        <head>
            <title>NFO Translation Monitor</title>
            <style>
                body {{ font-family: sans-serif; margin: 40px; background: #f4f4f9; }}
                table {{ width: 100%; border-collapse: collapse; background: white; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #4CAF50; color: white; }}
                .stats {{ margin-bottom: 20px; font-size: 1.2em; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>NFO Translation Monitor</h1>
            <div class="stats">Total Files Processed: {total}</div>
            <table>
                <tr><th>File Path</th><th>Last Processed (UTC)</th><th>Hash</th></tr>
                {"".join([f"<tr><td>{r.path}</td><td>{r.last_processed}</td><td>{r.hash[:8]}...</td></tr>" for r in records])}
            </table>
            <script>setTimeout(() => location.reload(), 5000);</script>
        </body>
    </html>
    """
    return html_content

# --- TRANSLATION & WATCHER LOGIC ---
def process_nfo(file_path):
    if not file_path.endswith(".nfo"): return
    db = SessionLocal()
    try:
        with open(file_path, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        record = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if record and record.hash == current_hash:
            return

        with open(file_path, "r", encoding="utf-8") as f:
            traditional = converter.convert(f.read())
        
        with open(file_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(traditional)

        with open(file_path, "rb") as f:
            new_hash = hashlib.md5(f.read()).hexdigest()

        if record: record.hash = new_hash
        else: db.add(FileRecord(path=file_path, hash=new_hash))
        db.commit()
    except Exception as e: print(f"Error: {e}")
    finally: db.close()

class WatcherHandler(FileSystemEventHandler):
    def on_modified(self, event): 
        if not event.is_directory: process_nfo(event.src_path)

def start_watcher():
    path = "/data"
    event_handler = WatcherHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True: time.sleep(1)
    except: observer.stop()

# Start Watcher in a separate thread
threading.Thread(target=start_watcher, daemon=True).start()