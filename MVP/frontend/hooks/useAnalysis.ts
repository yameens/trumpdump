'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LatestAnalysis, SSEAnalysisEvent } from '@/types/analysis';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || 'http://localhost:8000';
const POLL_INTERVAL = 30000; // 30 seconds fallback

interface UseAnalysisResult {
  analysis: LatestAnalysis | null;
  loading: boolean;
  error: string | null;
  isLive: boolean; // true if SSE connected, false if polling
  lastUpdated: Date | null;
}

export function useAnalysis(): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<LatestAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch latest analysis from API
  const fetchLatest = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/latest`);
      
      if (response.status === 404) {
        // No analysis available yet - not an error
        setAnalysis(null);
        setError(null);
        return null;
      }
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data: LatestAnalysis = await response.json();
      setAnalysis(data);
      setError(null);
      setLastUpdated(new Date());
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch analysis';
      setError(message);
      return null;
    }
  }, []);

  // Start polling fallback
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return; // Already polling
    
    console.log('[useAnalysis] Starting polling fallback (30s interval)');
    pollIntervalRef.current = setInterval(() => {
      fetchLatest();
    }, POLL_INTERVAL);
  }, [fetchLatest]);

  // Stop polling
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      console.log('[useAnalysis] Stopping polling');
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // Connect to SSE stream
  const connectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    console.log('[useAnalysis] Connecting to SSE stream...');
    const eventSource = new EventSource(`${BACKEND_URL}/stream`);
    eventSourceRef.current = eventSource;

    eventSource.addEventListener('connected', (event) => {
      console.log('[useAnalysis] SSE connected:', event.data);
      setIsLive(true);
      stopPolling(); // Stop polling if SSE connected
    });

    eventSource.addEventListener('analysis', (event) => {
      try {
        const data: SSEAnalysisEvent = JSON.parse(event.data);
        console.log('[useAnalysis] Received new analysis via SSE:', data.id);
        
        // Convert SSE event to LatestAnalysis format
        const newAnalysis: LatestAnalysis = {
          id: data.id,
          post_id: data.post_id,
          post: data.post,
          created_at_utc: Math.floor(Date.now() / 1000), // Use current time for SSE events
          relevance_score: data.relevance_score,
          top_vertical: data.top_vertical,
          top_vertical_conf: data.top_vertical_conf,
          verticals: data.verticals || [],
          tickers: data.tickers || [],
          base_case_summary: data.base_case_summary,
        };
        
        setAnalysis(newAnalysis);
        setLastUpdated(new Date());
        setError(null);
      } catch (err) {
        console.error('[useAnalysis] Failed to parse SSE event:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.error('[useAnalysis] SSE error:', err);
      setIsLive(false);
      eventSource.close();
      eventSourceRef.current = null;
      
      // Fall back to polling
      startPolling();
      
      // Try to reconnect SSE after a delay
      setTimeout(() => {
        if (!eventSourceRef.current) {
          connectSSE();
        }
      }, 5000);
    };

    return eventSource;
  }, [stopPolling, startPolling]);

  // Initial setup
  useEffect(() => {
    let mounted = true;

    const init = async () => {
      setLoading(true);
      
      // Fetch initial data
      await fetchLatest();
      
      if (mounted) {
        setLoading(false);
        // Connect to SSE for live updates
        connectSSE();
      }
    };

    init();

    // Cleanup on unmount
    return () => {
      mounted = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      stopPolling();
    };
  }, [fetchLatest, connectSSE, stopPolling]);

  return {
    analysis,
    loading,
    error,
    isLive,
    lastUpdated,
  };
}

