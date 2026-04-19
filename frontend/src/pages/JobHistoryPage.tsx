import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Download, Search, Filter, Loader2, CheckCircle2, XCircle, Clock, PlayCircle, Copy } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAppFeedback } from '@/components/feedback/useAppFeedback';
import { apiUrl, canonicalJobsRouteErrorMessage } from '@/utils/api';

interface Job {
  id: string;
  name: string;
  status: string;
  created_at: string;
  recipe_type: string;
  result?: any;
  progress_percent?: number;
  files_generated?: number;
  total_files_estimated?: number;
  current_stage?: string;
  started_at?: string;
  estimated_time_remaining?: string;
}

export function JobHistoryPage() {
  const feedback = useAppFeedback();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null);
  const isMountedRef = useRef(true);
  const navigate = useNavigate();
  const DEFAULT_LIMIT = 50;

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadJobs = useCallback(async (reset: boolean = false, currentOffsetOverride?: number) => {
    if (reset) {
      setOffset(0);
      setJobs([]);
    }

    const currentOffset = currentOffsetOverride !== undefined ? currentOffsetOverride : (reset ? 0 : offset);
    setLoadingMore(!reset);

    try {
      const params = new URLSearchParams();
      if (statusFilter) {
        params.append('status', statusFilter);
      }
      params.append('limit', DEFAULT_LIMIT.toString());
      params.append('offset', currentOffset.toString());

      const response = await fetch(apiUrl(`/api/v1/jobs?${params.toString()}`));
      if (!response.ok) {
        throw new Error(canonicalJobsRouteErrorMessage(`HTTP ${response.status}: ${response.statusText}`));
      }

      const data = await response.json();
      
      if (!isMountedRef.current) return;

      if (reset) {
        setJobs(data.jobs || []);
      } else {
        setJobs(prev => [...prev, ...(data.jobs || [])]);
      }

      setTotalCount(data.total_count || 0);
      setOffset(currentOffset + (data.jobs?.length || 0));
      
      setHasMore(data.jobs && data.jobs.length === DEFAULT_LIMIT);
    } catch (error) {
      console.error('Failed to load jobs:', error);
      if (isMountedRef.current) {
        feedback.error('Failed to load jobs', canonicalJobsRouteErrorMessage(error));
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [feedback, offset, statusFilter]);

  useEffect(() => {
    loadJobs(true, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const runningJobIds = useMemo(() => {
    return jobs.filter(j => j.status === 'running' || j.status === 'pending').map(j => j.id);
  }, [jobs]);

  useEffect(() => {
    if (runningJobIds.length === 0) return;

    const pollJobStatus = async (jobId: string) => {
      try {
        const response = await fetch(apiUrl(`/api/v1/jobs/${jobId}`));
        if (!response.ok) {
          return;
        }
        const updatedJob = await response.json();
        
        if (!isMountedRef.current) return;
        
        setJobs(prev => prev.map(j => 
          j.id === updatedJob.id ? { ...j, ...updatedJob } : j
        ));
      } catch (error) {
        console.error(`Failed to poll job ${jobId}:`, error);
      }
    };

    const interval = setInterval(() => {
      runningJobIds.forEach(jobId => {
        pollJobStatus(jobId);
      });
    }, 2000);

    return () => clearInterval(interval);
  }, [runningJobIds]);

  const handleDownload = useCallback(async (jobId: string, jobName: string) => {
    try {
      const response = await fetch(apiUrl(`/api/v1/datasets/${jobId}/download`));
      
      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        feedback.error('Download failed', errorText || 'The dataset ZIP could not be downloaded.');
        return;
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${jobName || jobId}.zip`;
      document.body.appendChild(a);
      a.click();
      
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
      feedback.error('Download failed', 'Failed to download dataset. Please try again.');
    }
  }, [feedback]);

  const handleExplore = useCallback((jobId: string) => {
    navigate(`/dataset-explorer?jobId=${jobId}`);
  }, [navigate]);

  const handleCopyJobId = useCallback(async (jobId: string, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    try {
      // Try modern clipboard API first
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(jobId);
        setCopiedJobId(jobId);
        setTimeout(() => {
          setCopiedJobId(null);
        }, 2000);
        return;
      }
      
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = jobId;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        const successful = document.execCommand('copy');
        if (successful) {
          setCopiedJobId(jobId);
          setTimeout(() => {
            setCopiedJobId(null);
          }, 2000);
        } else {
          throw new Error('execCommand copy failed');
        }
      } finally {
        document.body.removeChild(textArea);
      }
    } catch (err) {
      console.error('Failed to copy job ID:', err);
      feedback.error('Failed to copy job ID', `Please copy it manually: ${jobId}`);
    }
  }, [feedback]);

  const filteredJobs = useMemo(() => {
    if (!searchQuery) return jobs;
    const query = searchQuery.toLowerCase();
    return jobs.filter(job => 
      job.name.toLowerCase().includes(query) ||
      job.recipe_type.toLowerCase().includes(query) ||
      job.id.toLowerCase().includes(query)
    );
  }, [jobs, searchQuery]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Badge className="bg-green-100 text-green-800 border-green-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Completed
          </Badge>
        );
      case 'failed':
        return (
          <Badge className="bg-red-100 text-red-800 border-red-200">
            <XCircle className="w-3 h-3 mr-1" />
            Failed
          </Badge>
        );
      case 'running':
        return (
          <Badge className="bg-yellow-100 text-yellow-800 border-yellow-200">
            <PlayCircle className="w-3 h-3 mr-1" />
            Running
          </Badge>
        );
      case 'pending':
        return (
          <Badge className="bg-gray-100 text-gray-800 border-gray-200">
            <Clock className="w-3 h-3 mr-1" />
            Pending
          </Badge>
        );
      default:
        return (
          <Badge className="bg-gray-100 text-gray-800 border-gray-200">
            {status}
          </Badge>
        );
    }
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatRecipeType = (recipeType: string) => {
    return recipeType
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  if (loading && jobs.length === 0) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-teal-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-teal-500 pl-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Job History</h1>
        <p className="mt-2 text-slate-600">
          View and manage all your dataset generation jobs. Total: {totalCount} jobs
        </p>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 w-4 h-4" />
                <Input
                  placeholder="Search jobs by name, recipe type, or ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant={statusFilter === null ? "default" : "outline"}
                onClick={() => setStatusFilter(null)}
                size="sm"
              >
                <Filter className="w-4 h-4 mr-2" />
                All
              </Button>
              <Button
                variant={statusFilter === "completed" ? "default" : "outline"}
                onClick={() => setStatusFilter("completed")}
                size="sm"
              >
                Completed
              </Button>
              <Button
                variant={statusFilter === "running" ? "default" : "outline"}
                onClick={() => setStatusFilter("running")}
                size="sm"
              >
                Running
              </Button>
              <Button
                variant={statusFilter === "failed" ? "default" : "outline"}
                onClick={() => setStatusFilter("failed")}
                size="sm"
              >
                Failed
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Jobs List */}
      {filteredJobs.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <p className="text-slate-500">
              {searchQuery || statusFilter
                ? 'No jobs found matching your filters.'
                : 'No jobs found. Create your first dataset in the Builder.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredJobs.map((job) => (
            <Card key={job.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-lg font-semibold text-slate-900 truncate">
                        {job.name}
                      </h3>
                      {getStatusBadge(job.status)}
                    </div>
                    <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
                      <span>
                        <span className="font-medium">Created:</span> {formatDate(job.created_at)}
                      </span>
                      <span className="text-slate-300">•</span>
                      <span>
                        <span className="font-medium">Recipe:</span> {formatRecipeType(job.recipe_type)}
                      </span>
                      <span className="text-slate-300">•</span>
                      <span className="font-mono text-xs flex items-center gap-1.5">
                        <span>ID: {job.id.substring(0, 8)}...</span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleCopyJobId(job.id, e)}
                          className="h-6 w-6 p-0 hover:bg-slate-100 flex items-center justify-center transition-all"
                          title={copiedJobId === job.id ? "Copied!" : "Copy Job ID"}
                        >
                          {copiedJobId === job.id ? (
                            <CheckCircle2 className="w-4 h-4 text-green-600 animate-fadeIn" />
                          ) : (
                            <Copy className="w-4 h-4 text-slate-500 hover:text-slate-700 transition-colors" />
                          )}
                        </Button>
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    {job.status === 'completed' && (
                      <>
                        <Button
                          onClick={() => handleDownload(job.id, job.name)}
                          size="sm"
                          variant="outline"
                          className="flex items-center gap-2"
                        >
                          <Download className="w-4 h-4" />
                          Download
                        </Button>
                        <Button
                          onClick={() => handleExplore(job.id)}
                          size="sm"
                          className="flex items-center gap-2"
                        >
                          Explore
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Load More Button */}
          {hasMore && !loadingMore && (
            <div className="text-center pt-4">
              <Button
                onClick={() => loadJobs(false)}
                variant="outline"
                disabled={loadingMore}
              >
                Load More Jobs ({totalCount - jobs.length} remaining)
              </Button>
            </div>
          )}

          {loadingMore && (
            <div className="text-center pt-4">
              <Loader2 className="w-6 h-6 animate-spin text-blue-600 mx-auto" />
            </div>
          )}

          {!hasMore && jobs.length > 0 && (
            <div className="text-center pt-4 text-sm text-slate-500">
              All {totalCount} jobs loaded
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default JobHistoryPage;
