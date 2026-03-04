# NFO Monitor & Translator v1.5.5

A lightweight FastAPI-based tool to monitor `.nfo` files and automatically translate metadata (Title, Plot, Genre, etc.) between Simplified and Traditional Chinese using OpenCC and PostgreSQL.

---

## 🔄 Smart UI Auto-Refresh

The dashboard features **Smart Renewal** logic to optimize system resources and browser performance:

* **Idle State:** When the system is ready and no task is active, the page remains static.
* **Active State:** Once a scan is triggered (via Web UI or API), the server injects a `<meta http-equiv="refresh" content="3">` tag.
* **Auto-Stop:** The browser refreshes every 3 seconds to show live logs. Once the background task finishes, the refresh tag is removed automatically.



---

## 🚀 Automation & API Trigger

Version 1.5.5 uses a secure **POST** method for remote automation, allowing integration with other containers.

### API Specification
* **Endpoint:** `http://<server-ip>:8000/trigger`
* **Method:** `POST`
* **Content-Type:** `application/json`

### JSON Payload
The request must include your API key in the following format:
```json
{
  "key": "your_api_key_here"
}
```
---
### 🚀 Quick Start (Docker Compose)

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
	  
```
## 🗄️ Database Management

### Manual Database Creation
If you are using an existing PostgreSQL server and need to create a dedicated database for this project within the same instance:

1. **Access the Postgres Container:**
   ```bash
   docker exec -it <postgres_container_name> psql -U <username>
   CREATE DATABASE <POSTGRES_DB>;