import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { BarChart3, Clock, CheckCircle, XCircle, TrendingUp } from 'lucide-react';
import { useRequestCancellationWithDeps } from '@/hooks/useRequestCancellation';

interface PerformanceMetrics {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  success_rate: number;
  average_generation_time: number | null;
  total_topics_generated: number;
  total_maps_generated: number;
  total_size: number;
  jobs_by_status: {
    succeeded: number;
    failed: number;
    running: number;
    pending: number;
  };
}

interface TimelineData {
  date: string;
  jobs: number;
  completed: number;
  failed: number;
  total_time: number;
  total_topics: number;
}

export function PerformanceDashboard() {
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [timeline, setTimeline] = useState<TimelineData[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const isMountedRef = useRef(true);
  const abortController = useRequestCancellationWithDeps([days]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    loadMetrics();
    loadTimeline();
  }, [days]);

  const loadMetrics = async () => {
    try {
      const response = await fetch(`/api/v1/performance/metrics?days=${days}`, {
        signal: abortController.signal,
      });
      
      if (abortController.signal.aborted || !isMountedRef.current) {
        return;
      }
      
      if (response.ok) {
        const data = await response.json();
        if (!abortController.signal.aborted && isMountedRef.current) {
          setMetrics(data);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
      if (isMountedRef.current) {
        console.error('Failed to load metrics:', error);
      }
    } finally {
      if (isMountedRef.current && !abortController.signal.aborted) {
        setLoading(false);
      }
    }
  };

  const loadTimeline = async () => {
    try {
      const response = await fetch(`/api/v1/performance/timeline?days=${days}`, {
        signal: abortController.signal,
      });
      
      if (abortController.signal.aborted || !isMountedRef.current) {
        return;
      }
      
      if (response.ok) {
        const data = await response.json();
        if (!abortController.signal.aborted && isMountedRef.current) {
          setTimeline(data.timeline || []);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
      if (isMountedRef.current) {
        console.error('Failed to load timeline:', error);
      }
    }
  };

  const formatTime = (seconds: number | null) => {
    if (!seconds) return 'N/A';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  if (loading) {
    return <div className="text-center py-4">Loading performance metrics...</div>;
  }

  if (!metrics) {
    return <div className="text-center py-4 text-red-500">Failed to load metrics</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Performance Dashboard</h2>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-md border border-input bg-background px-3 py-2"
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Jobs</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.total_jobs}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.success_rate.toFixed(1)}%</div>
            <p className="text-xs text-muted-foreground">
              {metrics.completed_jobs} completed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Generation Time</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatTime(metrics.average_generation_time)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Topics</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.total_topics_generated.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {metrics.total_maps_generated} maps
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Status Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Jobs by Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <Badge variant="outline" className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-500" />
              Succeeded: {metrics.jobs_by_status.succeeded}
            </Badge>
            <Badge variant="outline" className="flex items-center gap-2">
              <XCircle className="h-3 w-3 text-red-500" />
              Failed: {metrics.jobs_by_status.failed}
            </Badge>
            <Badge variant="outline">
              Running: {metrics.jobs_by_status.running}
            </Badge>
            <Badge variant="outline">
              Pending: {metrics.jobs_by_status.pending}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Timeline Chart */}
      {timeline.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {timeline.map((day, idx) => (
                <div key={idx} className="flex items-center gap-4">
                  <div className="w-24 text-sm">{day.date}</div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <div
                        className="bg-blue-500 h-4 rounded"
                        style={{ width: `${(day.jobs / Math.max(...timeline.map(t => t.jobs))) * 100}%` }}
                      />
                      <span className="text-sm">{day.jobs} jobs</span>
                    </div>
                  </div>
                  <div className="text-sm text-gray-500">
                    {day.completed} completed, {day.failed} failed
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
