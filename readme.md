# 🎬 NFO Pro Translator

A high-performance, multi-architecture (AMD64/ARM64) Docker utility designed for NAS devices. It automatically monitors and translates NFO metadata between Simplified and Traditional Chinese while preserving XML structure.

## ✨ Features
* **Targeted Translation:** Only translates `<title>`, `<plot>`, `<outline>`, `<tag>`, `<genre>`, and `<series>` tags.
* **Dual Mode:** Supports both `s2t` (Simplified to Traditional) and `t2s` (Traditional to Simplified) via environment variables.
* **Lightweight Dashboard:** A No-JS Web UI to monitor processing progress in real-time.
* **Persistent History:** Uses PostgreSQL to track file hashes so files are never processed twice.

---

## 🚀 Quick Start (Docker Compose)

```yaml
version: '3.8'

services:
  nfo-postgres:
    image: postgres:15-alpine
    container_name: nfo-postgres
    environment:
      - POSTGRES_USER=nfo
      - POSTGRES_PASSWORD=nfo_pass
      - POSTGRES_DB=nfo_db
    volumes:
      - ./db_data:/var/lib/postgresql/data
    networks:
      - nfo-network

  nfo-translator:
    image: starducktea/nfo-translator:latest
    container_name: nfo-translator
    environment:
      - DATABASE_URL=postgresql://nfo:nfo_pass@nfo-postgres:5432/nfo_db
      - STARTUP_DELAY=60      
      - TRANS_MODE=s2t        
    volumes:
      - /share/CACHEDEV1_DATA/Multimedia:/data
    ports:
      - "8080:8080"
    depends_on:
      - nfo-postgres
    networks:
      - nfo-network

networks:
  nfo-network:
    driver: bridge