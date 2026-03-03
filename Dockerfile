FROM python:3.9-slim

# 1. Install system-level dependencies
# These are the "building blocks" that allow Python to compile 
# database drivers (Postgres) and translation engines (OpenCC) on ANY architecture.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    python3-dev \
    libopencc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copy requirements first (to speed up future builds)
COPY requirements.txt .

# 3. Install Python libraries
# On amd64, this usually downloads pre-built files.
# On arm64, this will use the 'build-essential' tools above to compile them locally.
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy your main.py and other files
COPY . .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]