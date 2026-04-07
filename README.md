# Project Onyx - Sync Engine & API (Backend)

This repository contains the asynchronous data ingestion engine for the Onyx Xbox Tracker. It is designed to safely consume the OpenXBL API, respect strict rate limits, and perform bulk upserts into a cloud PostgreSQL database without blocking the main web server.

## 🚀 Tech Stack
* **API Framework:** FastAPI (Python)
* **Background Queue:** Celery + Redis
* **ORM & Database:** SQLAlchemy 2.0 (Async), asyncpg, Neon Postgres
* **Containerization:** Docker & Docker Compose

## 🏗️ Architectural Decisions
1. **Asynchronous Task Queue (Celery):** Syncing a player's Xbox library can take several seconds to minutes due to API rate limits. FastAPI instantly returns a `202 Accepted` response to the frontend, dropping the heavy ingestion job into a Redis queue for a Celery worker to consume safely.
2. **Smart Delta Syncing:** To prevent redundant API calls, the worker compares the user's previously cached `current_gamerscore` with their live Gamerscore. It only fetches achievements for games that have registered actual progress.
3. **Relational Upserts:** Database writes use PostgreSQL's `ON CONFLICT DO UPDATE` clause. This ensures the background worker is completely idempotent and will never duplicate rows, simply updating locked/unlocked states as data arrives.
4. **The Legacy API Merge Strategy:** Microsoft's legacy Xbox 360 endpoints split catalog data and personal progress data. The backend intelligently detects Xbox 360 titles, triggers a merge strategy utilizing two separate endpoints, and constructs a unified achievement list in memory before saving.

## 🛠️ Local Development

### 1. Requirements
You must have Python 3.12+ and Docker (for Redis) installed.

### 2. Setup the Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory:
```text
DATABASE_URL=postgresql+asyncpg://[user]:[password]@[host]/[dbname]?sslmode=require
XBOX_API_KEY=your_openxbl_key
REDIS_URL=redis://localhost:6379/0
```

### 4. Start the Infrastructure
**Terminal 1: Start Redis**
```bash
docker run -d -p 6379:6379 redis:alpine
```

**Terminal 2: Start the Celery Worker**
```bash
celery -A tasks worker --loglevel=info
```

**Terminal 3: Start the FastAPI Server**
```bash
uvicorn main:app --reload --port 8000
```
API Documentation (Swagger UI) is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## 🐳 Production Deployment
This service is designed to be deployed via Docker Compose behind a reverse proxy (like Caddy or Nginx).
```bash
docker compose up -d --build
```
