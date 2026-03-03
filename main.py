import os, time, hashlib, threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import opencc
from sqlalchemy import create_engine, Column, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

# --- DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL")

# Retry logic for existing databases
engine = None
for i in range(5):
    try:
        engine = create_engine(DATABASE_URL)
        engine.connect()
        print("Successfully connected to the database.")
        break
    except OperationalError:
        print(f"Database not ready, retrying in 5s... ({i+1}/5)")
        time.sleep(5)

if not engine:
    raise Exception("Could not connect to the existing PostgreSQL database.")

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class FileRecord(Base):
    __tablename__ = "file_records"
    path = Column(String, primary_key=True)
    hash = Column(String)
    last_processed = Column(DateTime, default=func.now(), onupdate=func.now())

# This creates the table if it doesn't exist in your existing DB
Base.metadata.create_all(bind=engine)

converter = opencc.OpenCC('s2t')
app = FastAPI()

# --- WEB UI & WATCHER LOGIC (Same as before) ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    records = db.query(FileRecord).order_by(FileRecord.last_processed.desc()).limit(50).all()
    total = db.query(FileRecord).count()
    db.close()
    
    # HTML omitted for brevity, same as previous response...
    return f"<h1>Status: {total} files processed</h1>" # Simplified for example

def process_nfo(file_path):
    if not file_path.endswith(".nfo"): return
    db = SessionLocal()
    try:
        with open(file_path, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        record = db.query(FileRecord).filter(FileRecord.path == file_path).first()
        if record and record.hash == current_hash:
            return # Skip if already translated and unchanged

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        traditional = converter.convert(content)

        with open(file_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(traditional)

        # Re-hash after writing to prevent loops
        with open(file_path, "rb") as f:
            new_hash = hashlib.md5(f.read()).hexdigest()

        if record:
            record.hash = new_hash
        else:
            db.add(FileRecord(path=file_path, hash=new_hash))
        db.commit()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

# (Include WatcherHandler and start_watcher thread from previous code)