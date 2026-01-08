/**
 * TypeScript interfaces for the TrumpDump API responses.
 * These match the backend FastAPI Pydantic schemas.
 */

export interface PostInfo {
  id: number;
  url: string;
  title?: string;
  content_preview?: string;  // First 500 chars for preview
  content?: string;          // Full original post content
}

export interface MoveEstimate {
  horizon: string;
  expected_pct_range: string;
}

export interface TickerImpact {
  ticker_or_etf: string;
  direction_up_down_mixed: string;
  mechanism: string;
  confidence_0_1: number;
  conservative_move?: MoveEstimate;
  aggressive_move?: MoveEstimate;
}

export interface VerticalImpact {
  vertical: string;
  rationale: string;
  confidence_0_1: number;
}

export interface LatestAnalysis {
  id: number;
  post_id: number;
  post?: PostInfo;
  created_at_utc: number;
  relevance_score: number;
  top_vertical?: string;
  top_vertical_conf?: number;
  verticals: VerticalImpact[];
  tickers: TickerImpact[];
  base_case_summary?: string;
  conservative_case_summary?: string;
  aggressive_case_summary?: string;
}

/**
 * SSE event payload structure (from /stream endpoint)
 */
export interface SSEAnalysisEvent {
  id: number;
  post_id: number;
  relevance_score: number;
  top_vertical?: string;
  top_vertical_conf?: number;
  post?: PostInfo;
  verticals: VerticalImpact[];
  tickers: TickerImpact[];
  base_case_summary?: string;
}

/**
 * API error response structure
 */
export interface APIError {
  detail: {
    message: string;
    hint?: string;
    thresholds?: {
      min_score: number;
      min_conf: number;
    };
  };
}


