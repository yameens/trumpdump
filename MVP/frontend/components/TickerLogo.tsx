'use client';

import { useState } from 'react';

interface TickerLogoProps {
  ticker: string;
  size?: number;
}

const LOGO_DEV_KEY = process.env.NEXT_PUBLIC_LOGO_DEV_PUBLISHABLE_KEY;

export function TickerLogo({ ticker, size = 32 }: TickerLogoProps) {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Don't render if no API key configured
  if (!LOGO_DEV_KEY) {
    return (
      <div 
        className="ticker-logo-placeholder"
        style={{ width: size, height: size }}
      >
        {ticker.slice(0, 2)}
      </div>
    );
  }

  // Don't render broken images
  if (hasError) {
    return (
      <div 
        className="ticker-logo-placeholder"
        style={{ width: size, height: size }}
      >
        {ticker.slice(0, 2)}
      </div>
    );
  }

  const logoUrl = `https://img.logo.dev/ticker/${ticker}?token=${LOGO_DEV_KEY}&format=png`;

  return (
    <div className="ticker-logo-container" style={{ width: size, height: size }}>
      {isLoading && (
        <div 
          className="ticker-logo-placeholder loading"
          style={{ width: size, height: size }}
        >
          {ticker.slice(0, 2)}
        </div>
      )}
      <img
        src={logoUrl}
        alt={`${ticker} logo`}
        width={size}
        height={size}
        className={`ticker-logo ${isLoading ? 'hidden' : ''}`}
        onLoad={() => setIsLoading(false)}
        onError={() => {
          setHasError(true);
          setIsLoading(false);
        }}
      />
    </div>
  );
}

