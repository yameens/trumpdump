'use client';

import { useState } from 'react';
import type { LatestAnalysis } from '@/types/analysis';
import { TickerRow } from './TickerRow';

interface AnalysisCardProps {
  analysis: LatestAnalysis;
  isSecondary?: boolean;
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

export function AnalysisCard({ analysis, isSecondary = false }: AnalysisCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const postTitle = analysis.post?.title || 'Untitled Post';
  const postUrl = analysis.post?.url || '#';
  const postContent = analysis.post?.content;
  const contentPreview = analysis.post?.content_preview;
  
  const hasTickers = analysis.tickers && analysis.tickers.length > 0;

  return (
    <div className={`analysis-card ${isSecondary ? 'analysis-card-secondary' : ''}`}>
      {/* Header */}
      <div className="card-header">
        <h2>{isSecondary ? 'Last Impactful Analysis' : 'Latest Analysis'}</h2>
        <span className={`relevance-badge ${getRelevanceColor(analysis.relevance_score)}`}>
          {analysis.relevance_score}/100
        </span>
      </div>

      {/* Two Column Layout */}
      <div className="card-body">
        {/* LEFT COLUMN - Narrative/Story */}
        <div className="card-left">
          {/* Post Info */}
          <div className="post-info">
            <a href={postUrl} target="_blank" rel="noopener noreferrer" className="post-title">
              {postTitle}
            </a>
            <span className="post-timestamp">
              {formatTimestamp(analysis.created_at_utc)}
            </span>
          </div>

          {/* Collapsible Original Post Content */}
          {(contentPreview || postContent) && (
            <div className="original-post-section">
              <button 
                className="collapsible-toggle"
                onClick={() => setIsExpanded(!isExpanded)}
                aria-expanded={isExpanded}
              >
                <span className="toggle-icon">{isExpanded ? '▼' : '▶'}</span>
                <span>Original Post</span>
              </button>
              
              {isExpanded && (
                <div className="original-post-content">
                  <p>{postContent || contentPreview}</p>
                  <a 
                    href={postUrl} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="read-full-link"
                  >
                    Read full post on whitehouse.gov →
                  </a>
                </div>
              )}
              
              {!isExpanded && contentPreview && (
                <p className="content-preview">
                  {contentPreview.length > 200 
                    ? contentPreview.substring(0, 200) + '...' 
                    : contentPreview}
                </p>
              )}
            </div>
          )}

          {/* Base Case Summary */}
          {analysis.base_case_summary && (
            <div className="summary-section">
              <h3>Base Case</h3>
              <p>{analysis.base_case_summary}</p>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN - Impact Panel */}
        <div className="card-right">
          <div className="impact-panel">
            {/* Top Sector Impact */}
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

            {/* Tickers */}
            {hasTickers && (
              <div className="tickers-section">
                <h3>Ticker Impact</h3>
                <div className="tickers-list">
                  {analysis.tickers.map((ticker, index) => (
                    <TickerRow key={`${ticker.ticker_or_etf}-${index}`} ticker={ticker} />
                  ))}
                </div>
              </div>
            )}

            {/* No Tickers */}
            {!hasTickers && (
              <div className="no-tickers">
                <h3>No Specific Ticker Impact</h3>
                <p className="no-tickers-reason">
                  {analysis.base_case_summary 
                    ? `This analysis focuses on broader policy implications rather than specific securities.`
                    : 'This post does not contain direct market-moving information for specific securities.'}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="card-footer">
        <span className="analysis-id">Analysis ID: {analysis.id}</span>
      </div>
    </div>
  );
}

