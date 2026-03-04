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
  app:
    image: starducktea/nfo-translator:latest
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - PUID=1000
      - PGID=100
      - API_KEY=<YOUR_API_KEY>
      - TRANS_MODE=s2t
      - DATABASE_URL=postgresql://<POSTGRES_USER>:<POSTGRES_PASS>@db:5432/<POSTGRES_DB>