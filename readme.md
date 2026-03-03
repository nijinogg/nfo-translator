# 🎬 NFO Pro Translator v1.2.0

A high-performance, multi-architecture (AMD64/ARM64) Docker utility designed for QNAP and other NAS devices. It automatically monitors and translates NFO metadata between Simplified and Traditional Chinese while preserving XML structure.

## ✨ Features
* **Targeted Translation:** Only translates `<title>`, `<plot>`, `<outline>`, `<tag>`, `<genre>`, and `<series>` tags.
* **Dual Mode:** Supports both `s2t` (Simplified to Traditional) and `t2s` (Traditional to Simplified).
* **No-JS Dashboard:** A lightweight Web UI with auto-refresh to monitor progress without complex scripts.
* **Database-Backed:** Uses PostgreSQL to track file hashes, ensuring files are only processed once.
* **Smart Watcher:** Uses `watchdog` to detect new or modified files in real-time.

---

## 🚀 Quick Start (Docker Compose)

Copy this into your `nfo-translator.yml` and run `docker compose up -d`.

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
      - STARTUP_DELAY=60      # Wait 60s for DB to warm up
      - TRANS_MODE=s2t        # Use 's2t' or 't2s'
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