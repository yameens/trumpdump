'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LatestAnalysis, SSEAnalysisEvent } from '@/types/analysis';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || 'http://localhost:8000';
const POLL_INTERVAL = 30000; // 30 seconds fallback polling
const SAFETY_POLL_INTERVAL = 60000; // 60 seconds safety net polling (always runs)
const MAX_RECONNECT_DELAY = 30000; // 30 seconds max delay for exponential backoff
const INITIAL_RECONNECT_DELAY = 1000; // 1 second initial delay

interface UseAnalysisResult {
  analysis: LatestAnalysis | null;
  lastImpactful: LatestAnalysis | null;  // Most recent analysis WITH tickers
  loading: boolean;
  error: string | null;
  isLive: boolean; // true if SSE connected, false if polling
  lastUpdated: Date | null;
}

export function useAnalysis(): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<LatestAnalysis | null>(null);
  const [lastImpactful, setLastImpactful] = useState<LatestAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const safetyPollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch latest analysis with tickers (for "last impactful" card)
  const fetchLatestWithTickers = useCallback(async (): Promise<LatestAnalysis | null> => {
    try {
      const response = await fetch(`${BACKEND_URL}/latest-with-tickers`);
      
      if (response.status === 404) {
        return null;
      }
      
      if (!response.ok) {
        return null;
      }
      
      return await response.json();
    } catch {
      return null;
    }
  }, []);

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
      
      // If current analysis has no tickers, fetch the last impactful one
      if (!data.tickers || data.tickers.length === 0) {
        const impactful = await fetchLatestWithTickers();
        // Only set if it's a different analysis
        if (impactful && impactful.id !== data.id) {
          setLastImpactful(impactful);
        } else {
          setLastImpactful(null);
        }
      } else {
        // Current analysis has tickers, no need for lastImpactful
        setLastImpactful(null);
      }
      
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch analysis';
      setError(message);
      return null;
    }
  }, [fetchLatestWithTickers]);

  // Start fallback polling (when SSE is not connected)
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return; // Already polling
    
    console.log('[useAnalysis] Starting fallback polling (30s interval)');
    pollIntervalRef.current = setInterval(() => {
      fetchLatest();
    }, POLL_INTERVAL);
  }, [fetchLatest]);

  // Stop fallback polling
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      console.log('[useAnalysis] Stopping fallback polling');
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // Calculate exponential backoff delay
  const getReconnectDelay = useCallback(() => {
    const delay = Math.min(
      MAX_RECONNECT_DELAY,
      INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current)
    );
    return delay;
  }, []);

  // Connect to SSE stream with exponential backoff
  const connectSSE = useCallback(() => {
    // Clear any pending reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    console.log(`[useAnalysis] Connecting to SSE stream... (attempt ${reconnectAttemptsRef.current + 1})`);
    
    try {
      const eventSource = new EventSource(`${BACKEND_URL}/stream`);
      eventSourceRef.current = eventSource;

      eventSource.addEventListener('connected', (event) => {
        console.log('[useAnalysis] SSE connected:', event.data);
        setIsLive(true);
        reconnectAttemptsRef.current = 0; // Reset reconnect attempts on successful connection
        stopPolling(); // Stop fallback polling if SSE connected
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
          
          // Update lastImpactful if needed
          if (!newAnalysis.tickers || newAnalysis.tickers.length === 0) {
            fetchLatestWithTickers().then((impactful) => {
              if (impactful && impactful.id !== newAnalysis.id) {
                setLastImpactful(impactful);
              }
            });
          } else {
            setLastImpactful(null);
          }
        } catch (err) {
          console.error('[useAnalysis] Failed to parse SSE event:', err);
        }
      });

      eventSource.onerror = () => {
        console.error('[useAnalysis] SSE connection error');
        setIsLive(false);
        eventSource.close();
        eventSourceRef.current = null;
        
        // Fall back to polling while SSE is down
        startPolling();
        
        // Schedule reconnect with exponential backoff
        const delay = getReconnectDelay();
        reconnectAttemptsRef.current++;
        console.log(`[useAnalysis] Scheduling SSE reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connectSSE();
        }, delay);
      };

      return eventSource;
    } catch (err) {
      console.error('[useAnalysis] Failed to create EventSource:', err);
      startPolling();
      return null;
    }
  }, [stopPolling, startPolling, fetchLatestWithTickers, getReconnectDelay]);

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
        
        // Start safety net polling - always runs every 60s regardless of SSE
        // This ensures we never miss updates even if SSE silently fails
        console.log('[useAnalysis] Starting safety net polling (60s interval)');
        safetyPollIntervalRef.current = setInterval(() => {
          fetchLatest();
        }, SAFETY_POLL_INTERVAL);
      }
    };

    init();

    // Cleanup on unmount
    return () => {
      mounted = false;
      
      // Close SSE connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      
      // Clear reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      // Stop fallback polling
      stopPolling();
      
      // Stop safety net polling
      if (safetyPollIntervalRef.current) {
        clearInterval(safetyPollIntervalRef.current);
        safetyPollIntervalRef.current = null;
      }
    };
  }, [fetchLatest, connectSSE, stopPolling]);

  return {
    analysis,
    lastImpactful,
    loading,
    error,
    isLive,
    lastUpdated,
  };
}
