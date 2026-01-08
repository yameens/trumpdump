# TrumpDump Frontend

A Next.js frontend for displaying real-time White House market analysis.

## Features

- Real-time updates via Server-Sent Events (SSE)
- Automatic fallback to polling with exponential backoff
- Safety net polling (60s) ensures no missed updates
- Ticker logos via Logo.dev
- Responsive design
- Grayscale theme with red/green market indicators

## Prerequisites

- Node.js 18+ 
- Backend server running (locally or on Railway)

## Local Development

### 1. Start the backend first

From the repo root:
```bash
cd MVP
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

### 2. Install frontend dependencies

In a separate terminal:
```bash
cd MVP/frontend
npm install
```

### 3. Create environment file

Create `.env.local` in the frontend directory:

```env
# Backend API URL (default: http://localhost:8000)
NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8000

# Logo.dev Publishable Key (client-safe, used for ticker logos)
# Get your key at https://logo.dev
NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY=your_publishable_key_here

# Logo.dev Secret Key (server-only, used for brand search API)
# Only needed if you want to resolve company names to domains
LOGO_DEV_SECRET_KEY=your_secret_key_here
```

### 4. Run the development server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Environment Variables

| Variable | Required | Scope | Description |
|----------|----------|-------|-------------|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | No | Client | Backend API URL. Defaults to `http://localhost:8000` |
| `NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY` | No | Client | Logo.dev public key for ticker images. If not set, shows placeholder |
| `LOGO_DEV_SECRET_KEY` | No | Server | Logo.dev secret key for brand search. Only needed for company name → domain resolution |

---

## Production Deployment (Vercel)

### 1. Push to GitHub

Make sure your code is pushed to a GitHub repository.

### 2. Import to Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click "New Project"
3. Import your GitHub repository
4. **Root Directory**: Set to `frontend` (important!)
5. Framework will be auto-detected as Next.js

### 3. Configure Environment Variables

In Vercel project settings, add these environment variables:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | `https://your-app.railway.app` (your Railway backend URL) |
| `NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY` | Your Logo.dev publishable key |
| `LOGO_DEV_SECRET_KEY` | Your Logo.dev secret key |

### 4. Deploy

Click "Deploy" - Vercel will build and deploy automatically.

Your frontend will be available at `https://your-project.vercel.app`

### 5. Update Backend CORS

In your Railway backend environment variables, add your Vercel domain to `ALLOWED_ORIGINS`:

```
ALLOWED_ORIGINS=https://your-project.vercel.app,http://localhost:3000
```

---

## Production Build (Self-hosted)

```bash
npm run build
npm run start
```

---

## Architecture

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Main page
│   ├── globals.css         # Global styles
│   └── api/
│       └── logo-domain/
│           └── route.ts    # Server-side brand search
├── components/
│   ├── AnalysisCard.tsx    # Main analysis display
│   ├── TickerRow.tsx       # Individual ticker
│   └── TickerLogo.tsx      # Ticker logo image
├── hooks/
│   └── useAnalysis.ts      # SSE + fetch logic
├── types/
│   └── analysis.ts         # TypeScript interfaces
├── vercel.json             # Vercel deployment config
└── public/
    ├── trumptitleFIX.png   # Title image
    └── ezgif.com-reverse.gif # Overlay GIF
```

---

## API Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /latest` | Fetch latest relevant analysis |
| `GET /latest-with-tickers` | Fetch latest analysis with ticker impacts |
| `GET /stream` | Server-Sent Events for real-time updates |

---

## Data Flow

```
1. Page Load
   └── Fetch /latest from backend
   └── Open SSE connection to /stream
   └── Start safety net polling (60s interval)

2. SSE Connected
   └── Stop fallback polling
   └── Receive real-time updates
   └── Safety net polling continues (catches any misses)

3. SSE Disconnected
   └── Start fallback polling (30s interval)
   └── Exponential backoff reconnection (1s → 2s → 4s → ... → 30s max)
   └── Auto-reconnect to SSE when available

4. New Analysis Received
   └── Update UI immediately
   └── If no tickers, fetch /latest-with-tickers for "last impactful"
```

---

## Real-time Updates

The frontend uses a robust approach to ensure you never miss an update:

1. **SSE (Primary)**: Real-time push notifications from backend
2. **Fallback Polling**: 30s interval when SSE disconnects
3. **Safety Net Polling**: 60s interval that always runs

### SSE Reconnection

When SSE disconnects, the frontend uses exponential backoff:
- Initial delay: 1 second
- Doubles each attempt: 1s → 2s → 4s → 8s → 16s → 30s (max)
- Resets to 1s on successful reconnection

---

## Troubleshooting

### Frontend can't connect to backend

**CORS Error in Console:**
- Check backend `ALLOWED_ORIGINS` includes your frontend URL
- For local dev: `http://localhost:3000`
- For production: `https://your-project.vercel.app`

**Network Error:**
- Verify backend is running
- Check `NEXT_PUBLIC_BACKEND_BASE_URL` is correct
- For production, ensure Railway backend is deployed

### No ticker logos showing

- Check `NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY` is set
- Logo.dev may not have logos for all tickers/ETFs

### SSE not connecting

- Check browser console for errors
- SSE requires backend to support long-lived connections
- Works on Railway, may not work on Vercel serverless

### 404 on /latest

- No relevant analyses in database yet
- Wait for scheduler to find and analyze a new post
- Or trigger manual poll: `curl -X POST http://localhost:8000/admin/scheduler/poll`

---

## Development Commands

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run production build locally
npm run start

# Lint code
npm run lint
```
