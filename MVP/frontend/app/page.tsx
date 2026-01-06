'use client';

import { useAnalysis } from '@/hooks/useAnalysis';
import { AnalysisCard } from '@/components/AnalysisCard';

export default function Home() {
  const { analysis, loading, error, isLive, lastUpdated } = useAnalysis();

  return (
    <main className="container">
      {/* Title Section - GIF above Title */}
      <div className="title-section">
        <img
          src="/ezgif.com-reverse.gif"
          alt=""
          className="trump-gif"
        />
        <img
          src="/trumpdumpTITLE.png"
          alt="TrumpDump"
          className="title-image"
        />
      </div>

      {/* Status Bar */}
      <div className="status-bar">
        <span className={`status-indicator ${isLive ? 'live' : 'polling'}`}>
          {isLive ? '● LIVE' : '○ Polling'}
        </span>
        {lastUpdated && (
          <span className="last-updated">
            Last updated: {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Main Content */}
      <div className="content">
        {loading && (
          <div className="loading">
            <div className="spinner" />
            <p>Loading latest analysis...</p>
          </div>
        )}

        {error && (
          <div className="error-card">
            <h3>Error</h3>
            <p>{error}</p>
          </div>
        )}

        {!loading && !analysis && !error && (
          <div className="no-analysis">
            <h3>No Analysis Available</h3>
            <p>Waiting for the first relevant White House post analysis...</p>
            <p className="hint">The system will automatically update when new analysis is available.</p>
          </div>
        )}

        {analysis && <AnalysisCard analysis={analysis} />}
      </div>

      {/* Footer */}
      <footer className="footer">
        <p>TrumpDump MVP - Real-time White House Market Analysis</p>
      </footer>
    </main>
  );
}
