'use client';

import type { LatestAnalysis } from '@/types/analysis';
import { TickerRow } from './TickerRow';

interface AnalysisCardProps {
  analysis: LatestAnalysis;
}

function formatTimestamp(utcSeconds: number): string {
  const date = new Date(utcSeconds * 1000);
  return date.toLocaleString();
}

function getRelevanceColor(score: number): string {
  if (score >= 75) return 'relevance-high';
  if (score >= 50) return 'relevance-medium';
  return 'relevance-low';
}

export function AnalysisCard({ analysis }: AnalysisCardProps) {
  const postTitle = analysis.post?.title || 'Untitled Post';
  const postUrl = analysis.post?.url || '#';

  return (
    <div className="analysis-card">
      {/* Header */}
      <div className="card-header">
        <h2>Latest Analysis</h2>
        <span className={`relevance-badge ${getRelevanceColor(analysis.relevance_score)}`}>
          {analysis.relevance_score}/100
        </span>
      </div>

      {/* Post Info */}
      <div className="post-info">
        <a href={postUrl} target="_blank" rel="noopener noreferrer" className="post-title">
          {postTitle}
        </a>
        <span className="post-timestamp">
          {formatTimestamp(analysis.created_at_utc)}
        </span>
      </div>

      {/* Top Vertical */}
      {analysis.top_vertical && (
        <div className="vertical-section">
          <h3>Top Sector Impact</h3>
          <div className="vertical-info">
            <span className="vertical-name">{analysis.top_vertical}</span>
            {analysis.top_vertical_conf !== undefined && (
              <span className="vertical-confidence">
                {(analysis.top_vertical_conf * 100).toFixed(0)}% confidence
              </span>
            )}
          </div>
        </div>
      )}

      {/* Base Case Summary */}
      {analysis.base_case_summary && (
        <div className="summary-section">
          <h3>Base Case</h3>
          <p>{analysis.base_case_summary}</p>
        </div>
      )}

      {/* Tickers */}
      {analysis.tickers && analysis.tickers.length > 0 && (
        <div className="tickers-section">
          <h3>Ticker Impact Analysis</h3>
          <div className="tickers-list">
            {analysis.tickers.map((ticker, index) => (
              <TickerRow key={`${ticker.ticker_or_etf}-${index}`} ticker={ticker} />
            ))}
          </div>
        </div>
      )}

      {/* No Tickers */}
      {(!analysis.tickers || analysis.tickers.length === 0) && (
        <div className="no-tickers">
          <p>No specific ticker impacts identified</p>
        </div>
      )}

      {/* Analysis ID */}
      <div className="card-footer">
        <span className="analysis-id">Analysis ID: {analysis.id}</span>
      </div>
    </div>
  );
}

