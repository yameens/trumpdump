# TrumpDump Backend

FastAPI backend for real-time White House market analysis.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Setup](#environment-setup)
- [Running the Server](#running-the-server)
- [API Endpoints](#api-endpoints)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Database](#database)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Python 3.10+** (tested with 3.11, 3.12)
- **pip** or **pip3**
- **OpenAI API Key** with access to `gpt-4o-mini` and `o3-mini` models

Check your Python version:
```bash
python3 --version
```

---

## Quick Start

```bash
# 1. Navigate to MVP directory
cd MVP

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# 4. Install dependencies
pip install -r backend/requirements.txt

# 5. Create .env file with your OpenAI key
echo "OPENAI_API_KEY=sk-your-key-here" > .env

# 6. Start the server
uvicorn backend.app.main:app --reload --port 8000
```

Server will be running at: **http://localhost:8000**

---

## Environment Setup

### 1. Create Virtual Environment

Always use a virtual environment to avoid dependency conflicts:

```bash
cd MVP
python3 -m venv venv
```

### 2. Activate Virtual Environment

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt when activated.

### 3. Install Dependencies

```bash
pip install -r backend/requirements.txt
```

This installs:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `apscheduler` - Background job scheduler
- `requests` - HTTP client for scraping
- `beautifulsoup4` - HTML parsing
- `openai` - OpenAI API client
- `python-dotenv` - Environment variable loading
- `psycopg2-binary` - PostgreSQL driver (for production)
- `slowapi` - Rate limiting

### 4. Configure Environment Variables

Create a `.env` file in the `MVP/` directory:

```bash
# MVP/.env

# Required: Your OpenAI API key
OPENAI_API_KEY=sk-proj-your-key-here

# Optional: Override default models
FACTS_MODEL=gpt-4o-mini      # Model for fact extraction (default: gpt-4o-mini)
MARKET_MODEL=o3-mini         # Model for market analysis (default: o3-mini)

# Optional: Scheduler configuration
POLL_INTERVAL_SECONDS=60     # How often to check for new posts (default: 60)
SKIP_ANALYSIS=false          # Set to "true" to skip OpenAI calls (for testing)
DISABLE_SCHEDULER=false      # Set to "true" to disable auto-polling

# Optional: Security (for production)
ADMIN_API_KEY=               # API key for /admin/* endpoints
ALLOWED_ORIGINS=http://localhost:3000  # Comma-separated CORS origins
```

**Important:** The `.env` file is gitignored. Never commit your API keys!

---

## Running the Server

### Development Mode (with auto-reload)

```bash
cd MVP
source venv/bin/activate
uvicorn backend.app.main:app --reload --port 8000
```

### Production Mode

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Verify Server is Running

```bash
curl http://localhost:8000/
```

Expected response:
```json
{"status":"ok","version":"0.2.0"}
```

**Health check with details:**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "version": "0.2.0",
  "database": "sqlite",
  "database_connected": true,
  "scheduler_running": true
}
```

---

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| GET | `/` | Basic status | - |
| GET | `/health` | Detailed health check | - |
| GET | `/latest` | Get latest relevant analysis | 60/min |
| GET | `/latest-with-tickers` | Get latest analysis with ticker impacts | 60/min |
| GET | `/history` | Get recent analyses | 30/min |
| GET | `/analysis/{id}` | Get specific analysis by ID | 60/min |
| GET | `/stream` | Server-Sent Events for real-time updates | - |

### Admin Endpoints

Protected by `X-API-Key` header when `ADMIN_API_KEY` is set.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/scheduler/status` | Check scheduler status |
| POST | `/admin/scheduler/poll` | Manually trigger a poll |
| GET | `/admin/sse/status` | Check SSE subscriber count |
| POST | `/admin/sse/test` | Send test event to SSE subscribers |

### Example Requests

**Get latest analysis:**
```bash
curl http://localhost:8000/latest
```

**Get latest with tickers:**
```bash
curl http://localhost:8000/latest-with-tickers
```

**Get history (last 20):**
```bash
curl "http://localhost:8000/history?limit=20"
```

**Manually trigger poll (with API key):**
```bash
curl -X POST http://localhost:8000/admin/scheduler/poll \
  -H "X-API-Key: your-admin-key"
```

**Connect to SSE stream:**
```bash
curl -N http://localhost:8000/stream
```

---

## Architecture

```
MVP/
├── backend/
│   ├── __init__.py
│   ├── requirements.txt          # Python dependencies
│   ├── Procfile                  # Railway deployment
│   ├── runtime.txt               # Python version for Railway
│   ├── README.md                 # This file
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI app & endpoints
│       ├── db.py                 # Database helpers (SQLite/PostgreSQL)
│       └── services/
│           ├── __init__.py
│           ├── analyzer.py       # OpenAI analysis logic
│           ├── events.py         # SSE event broadcasting
│           ├── relevance.py      # Heuristic filtering
│           ├── scheduler.py      # Background polling job
│           └── whitehouse_scraper.py  # Web scraper
├── trumpdump.db                  # SQLite database (local only)
└── .env                          # Environment variables
```

### Data Flow

```
1. Scheduler polls whitehouse.gov every 30-60 seconds
                    ↓
2. New post detected → Stored in database
                    ↓
3. Heuristic check (is it market-relevant?)
                    ↓
4. If relevant → OpenAI analysis (facts → market impact)
                    ↓
5. Analysis stored in database
                    ↓
6. SSE broadcast to connected clients
                    ↓
7. Frontend displays new analysis
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string (uses SQLite if empty) |
| `OPENAI_API_KEY` | - | **Required** for analysis |
| `POLL_INTERVAL_SECONDS` | 60 | Seconds between polls |
| `SKIP_ANALYSIS` | false | Skip OpenAI calls (testing) |
| `DISABLE_SCHEDULER` | false | Disable automatic polling |
| `ALLOWED_ORIGINS` | localhost:3000 | Comma-separated CORS origins |
| `ADMIN_API_KEY` | - | API key for /admin/* endpoints |

### Model Options

| Variable | Default | Description |
|----------|---------|-------------|
| `FACTS_MODEL` | gpt-4o-mini | Model for fact extraction |
| `MARKET_MODEL` | o3-mini | Model for market analysis (supports reasoning) |

### Relevance Thresholds

The `/latest` endpoint filters by:
- `min_score`: Minimum relevance score (default: 50)
- `min_conf`: Minimum vertical confidence (default: 0.65)

Override with query params:
```bash
curl "http://localhost:8000/latest?min_score=30&min_conf=0.5"
```

---

## Database

### Local Development (SQLite)

The backend uses **SQLite** stored at `MVP/trumpdump.db`.

### Production (PostgreSQL)

Set `DATABASE_URL` environment variable to use PostgreSQL:
```
DATABASE_URL=postgresql://user:password@host:port/database
```

The backend automatically detects which database to use.

### Tables

**whitehouse_posts**
- `id` - Primary key
- `url` - Unique post URL
- `title` - Post title
- `content` - Full post content
- `scraped_at_utc` - Unix timestamp

**analyses**
- `id` - Primary key
- `post_id` - Foreign key to whitehouse_posts
- `created_at_utc` - Unix timestamp
- `relevance_score` - 0-100 score
- `market_json` - Full analysis JSON
- `tickers_json` - Extracted ticker data
- `top_vertical` - Top sector impacted
- `top_vertical_conf` - Confidence 0-1

### View Database (SQLite)

```bash
cd MVP
sqlite3 trumpdump.db

# List tables
.tables

# View recent posts
SELECT id, title, scraped_at_utc FROM whitehouse_posts ORDER BY id DESC LIMIT 5;

# View analyses
SELECT id, post_id, relevance_score, top_vertical FROM analyses ORDER BY id DESC LIMIT 5;

# Exit
.quit
```

### Reset Database

To start fresh, delete the database file:
```bash
rm MVP/trumpdump.db
```

It will be recreated on next server start.

---

## Production Deployment

### Railway Deployment

1. **Create Railway account** at [railway.app](https://railway.app)

2. **Create a new project** and add PostgreSQL service

3. **Connect your GitHub repo** to Railway

4. **Set environment variables** in Railway dashboard:

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | Auto-provided by Railway PostgreSQL |
   | `OPENAI_API_KEY` | Your OpenAI key |
   | `POLL_INTERVAL_SECONDS` | `30` |
   | `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app,http://localhost:3000` |
   | `ADMIN_API_KEY` | Generate a secure random string |

5. **Deploy** - Railway will use the `Procfile`:
   ```
   web: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
   ```

6. **Verify deployment:**
   ```bash
   curl https://your-app.railway.app/health
   ```

### Deployment Files

- `Procfile` - Tells Railway how to start the server
- `runtime.txt` - Specifies Python version (3.11)
- `requirements.txt` - Python dependencies

### CORS Configuration

For production, set `ALLOWED_ORIGINS` to include your frontend domain:
```
ALLOWED_ORIGINS=https://trumpdump.vercel.app,http://localhost:3000
```

### Rate Limiting

The API has built-in rate limiting:
- `/latest`: 60 requests/minute
- `/latest-with-tickers`: 60 requests/minute
- `/history`: 30 requests/minute
- `/analysis/{id}`: 60 requests/minute

---

## Troubleshooting

### Server won't start

**Error: `ModuleNotFoundError: No module named 'fastapi'`**
```bash
# Make sure venv is activated
source venv/bin/activate
pip install -r backend/requirements.txt
```

**Error: `Missing OPENAI_API_KEY`**
```bash
# Create .env file in MVP/ directory
echo "OPENAI_API_KEY=sk-your-key" > .env
```

### OpenAI API errors

**Error: `reasoning.effort is not supported`**
- This means you're using the wrong model. Make sure `MARKET_MODEL=o3-mini` or remove reasoning.

**Error: `RateLimitError`**
- You've hit OpenAI rate limits. Wait and retry, or upgrade your plan.

### Database errors

**Error: `no such table: analyses`**
- Database migrations run automatically on startup. Restart the server.

**Error: `could not connect to server`** (PostgreSQL)
- Check your `DATABASE_URL` is correct
- Ensure PostgreSQL service is running

### CORS errors (from frontend)

The backend allows origins from `ALLOWED_ORIGINS` environment variable.
Default: `http://localhost:3000`

For production, add your Vercel domain:
```
ALLOWED_ORIGINS=https://trumpdump.vercel.app,http://localhost:3000
```

### Check server logs

The server logs all activity:
```
INFO:backend.app.services.scheduler:🔄 Polling White House for new posts...
INFO:backend.app.services.scheduler:📰 NEW POST: [title]
INFO:backend.app.services.scheduler:✅ Heuristic passed
INFO:backend.app.services.analyzer:🧠 Running OpenAI analysis...
INFO:backend.app.services.scheduler:💾 Analysis stored with ID: X
```

---

## Development Commands

```bash
# Activate environment
source venv/bin/activate

# Run server with auto-reload
uvicorn backend.app.main:app --reload --port 8000

# Run a single poll manually
curl -X POST http://localhost:8000/admin/scheduler/poll

# Test SSE connection
curl -N http://localhost:8000/stream

# Check scheduler status
curl http://localhost:8000/admin/scheduler/status

# Deactivate environment when done
deactivate
```

---

## Support

For issues or questions:
1. Check the logs for error messages
2. Verify your `.env` file has the correct API key
3. Make sure you're running from the `MVP/` directory
4. Ensure virtual environment is activated
