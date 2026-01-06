# TrumpDump Frontend

A Next.js frontend for displaying real-time White House market analysis.

## Features

- Real-time updates via Server-Sent Events (SSE)
- Automatic fallback to polling if SSE fails
- Ticker logos via Logo.dev
- Responsive design
- Dark theme

## Prerequisites

- Node.js 18+ 
- Backend server running at `http://localhost:8000` (or configured URL)

## Setup

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Create environment file `.env.local` in the frontend directory:

```bash
touch .env.local
```

3. Add your configuration to `.env.local`:

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

### Environment Variables

| Variable | Required | Scope | Description |
|----------|----------|-------|-------------|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | No | Client | Backend API URL. Defaults to `http://localhost:8000` |
| `NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY` | No | Client | Logo.dev public key for ticker images. If not set, shows placeholder |
| `LOGO_DEV_SECRET_KEY` | No | Server | Logo.dev secret key for brand search. Only needed for company name → domain resolution |

## Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Production Build

```bash
npm run build
npm run start
```

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
└── public/
    ├── trumpdumpTITLE.png  # Title image
    └── ezgif.com-reverse.gif # Overlay GIF
```

## API Endpoints Used

- `GET /latest` - Fetch latest relevant analysis
- `GET /stream` - Server-Sent Events for real-time updates

## Data Flow

1. On page load, fetches `/latest` from backend
2. Opens SSE connection to `/stream` for live updates
3. If SSE fails, falls back to polling `/latest` every 30 seconds
4. When new analysis arrives (via SSE or polling), UI updates automatically

