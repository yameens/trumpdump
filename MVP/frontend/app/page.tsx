'use client';

import { useAnalysis } from '@/hooks/useAnalysis';
import { AnalysisCard } from '@/components/AnalysisCard';

export default function Home() {
  const { analysis, lastImpactful, loading, error, isLive, lastUpdated } = useAnalysis();

  const currentHasNoTickers = analysis && (!analysis.tickers || analysis.tickers.length === 0);

  return (
    <main className="container">
      {/* Title Section - GIF positioned top-right overlapping title */}
      <div className="title-section">
      <img
          src="/ezgif.com-reverse.gif"
          alt=""
          className="trump-gif"
        />
        <img
          src="/trumptitleFIX.png"
          alt="TrumpDump"
          className="title-image"
        />
      </div>

      {/* Status Bar */}
     

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

        {/* Current Analysis */}
        {analysis && <AnalysisCard analysis={analysis} />}

        {/* Last Impactful Analysis */}
        {currentHasNoTickers && lastImpactful && (
          <div className="last-impactful-section">
            <p className="last-impactful-intro">
              Looking for actionable ticker insights? Here's the most recent analysis with specific market recommendations:
            </p>
            <AnalysisCard analysis={lastImpactful} isSecondary={true} />
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="footer">
        <p>TrumpDump, White House Market Analysis</p>
      </footer>
    </main>
  );
}
