'use client';

import type { TickerImpact } from '@/types/analysis';
import { TickerLogo } from './TickerLogo';

interface TickerRowProps {
  ticker: TickerImpact;
}

function getDirectionEmoji(direction: string): string {
  switch (direction.toLowerCase()) {
    case 'up':
      return '↑';
    case 'down':
      return '↓';
    case 'mixed':
      return '↕';
    default:
      return '?';
  }
}

function getDirectionClass(direction: string): string {
  switch (direction.toLowerCase()) {
    case 'up':
      return 'direction-up';
    case 'down':
      return 'direction-down';
    case 'mixed':
      return 'direction-mixed';
    default:
      return 'direction-unknown';
  }
}

export function TickerRow({ ticker }: TickerRowProps) {
  const conservativeRange = ticker.conservative_move?.expected_pct_range || 'N/A';
  const conservativeHorizon = ticker.conservative_move?.horizon || '';
  const aggressiveRange = ticker.aggressive_move?.expected_pct_range || 'N/A';
  const aggressiveHorizon = ticker.aggressive_move?.horizon || '';

  return (
    <div className="ticker-row">
      {/* Ticker Header */}
      <div className="ticker-header">
        <TickerLogo ticker={ticker.ticker_or_etf} />
        <span className="ticker-symbol">{ticker.ticker_or_etf}</span>
        <span className={`ticker-direction ${getDirectionClass(ticker.direction_up_down_mixed)}`}>
          {getDirectionEmoji(ticker.direction_up_down_mixed)} {ticker.direction_up_down_mixed}
        </span>
        <span className="ticker-confidence">
          {(ticker.confidence_0_1 * 100).toFixed(0)}% conf
        </span>
      </div>

      {/* Move Estimates */}
      <div className="ticker-moves">
        <div className="move-estimate conservative">
          <span className="move-label">Conservative:</span>
          <span className="move-range">{conservativeRange}</span>
          {conservativeHorizon && (
            <span className="move-horizon">({conservativeHorizon})</span>
          )}
        </div>
        <div className="move-estimate aggressive">
          <span className="move-label">Aggressive:</span>
          <span className="move-range">{aggressiveRange}</span>
          {aggressiveHorizon && (
            <span className="move-horizon">({aggressiveHorizon})</span>
          )}
        </div>
      </div>

      {/* Mechanism */}
      {ticker.mechanism && (
        <div className="ticker-mechanism">
          <span className="mechanism-label">Mechanism:</span>
          <span className="mechanism-text">{ticker.mechanism}</span>
        </div>
      )}
    </div>
  );
}

