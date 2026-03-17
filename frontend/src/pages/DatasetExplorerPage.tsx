import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DatasetExplorer } from '@/components/DatasetExplorer';
import { Loader2, FolderOpen } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

interface Job {
  id: string;
  name: string;
  status: string;
  created_at: string;
  recipe_type: string;
}

export function DatasetExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobIdFromUrl = searchParams.get('jobId');
  
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(jobIdFromUrl || null);
  const [loading, setLoading] = useState(true);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    loadCompletedJobs();
  }, []);

  useEffect(() => {
    if (jobIdFromUrl && jobIdFromUrl !== selectedJobId) {
      setSelectedJobId(jobIdFromUrl);
    }
  }, [jobIdFromUrl]);

  const loadCompletedJobs = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch only completed jobs
      const response = await fetch('/api/v1/jobs?status=completed');
      if (!response.ok) {
        throw new Error(`Failed to load jobs: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (!isMountedRef.current) return;

      setJobs(data.jobs || []);

      // If jobId is in URL but not in the list, still allow it (might be a valid job)
      if (jobIdFromUrl && !data.jobs?.some((j: Job) => j.id === jobIdFromUrl)) {
        // Job might exist but not be in completed status, allow selection anyway
        setSelectedJobId(jobIdFromUrl);
      } else if (jobIdFromUrl && data.jobs?.some((j: Job) => j.id === jobIdFromUrl)) {
        setSelectedJobId(jobIdFromUrl);
      } else if (!selectedJobId && data.jobs && data.jobs.length > 0) {
        // Auto-select first job if none selected
        setSelectedJobId(data.jobs[0].id);
      }
    } catch (error) {
      console.error('Failed to load jobs:', error);
      if (isMountedRef.current) {
        alert('Failed to load completed jobs. Please try again.');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [jobIdFromUrl, selectedJobId]);

  const handleJobSelect = useCallback((jobId: string) => {
    setSelectedJobId(jobId);
    setSearchParams({ jobId });
  }, [setSearchParams]);

  const selectedJob = jobs.find(j => j.id === selectedJobId);

  const formatRecipeType = (recipeType: string) => {
    return recipeType
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Dataset Explorer</h1>
        <p className="text-slate-600">
          Browse and explore your generated datasets. Select a completed job to view its structure and files.
        </p>
      </div>

      {/* Job Selector */}
      <Card>
        <CardHeader>
          <CardTitle>Select Dataset</CardTitle>
          <CardDescription>
            Choose a completed job to explore its dataset structure
          </CardDescription>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <div className="text-center py-8">
              <FolderOpen className="w-12 h-12 text-slate-400 mx-auto mb-4" />
              <p className="text-slate-500 mb-2">No completed jobs found</p>
              <p className="text-sm text-slate-400">
                Create and complete a dataset generation job in the Builder to explore it here.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Available Datasets ({jobs.length})
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {jobs.map((job) => (
                  <Button
                    key={job.id}
                    variant={selectedJobId === job.id ? "default" : "outline"}
                    onClick={() => handleJobSelect(job.id)}
                    className="justify-start h-auto py-3 px-4"
                  >
                    <div className="text-left w-full">
                      <div className="font-semibold text-sm mb-1 truncate">
                        {job.name}
                      </div>
                      <div className="text-xs text-slate-500">
                        {formatRecipeType(job.recipe_type)}
                      </div>
                      <div className="text-xs text-slate-400 mt-1 font-mono">
                        {job.id.substring(0, 8)}...
                      </div>
                    </div>
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dataset Explorer */}
      {selectedJobId && selectedJob ? (
        <Card>
          <CardHeader>
            <CardTitle>Dataset Structure</CardTitle>
            <CardDescription>
              Exploring: {selectedJob.name} ({formatRecipeType(selectedJob.recipe_type)})
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DatasetExplorer jobId={selectedJobId} jobName={selectedJob.name} />
          </CardContent>
        </Card>
      ) : selectedJobId && !selectedJob ? (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <p className="text-slate-500">
              Selected job not found in completed jobs list. It may still be running or may have failed.
            </p>
            <p className="text-sm text-slate-400 mt-2">
              Job ID: {selectedJobId.substring(0, 8)}...
            </p>
            <div className="mt-4">
              <DatasetExplorer jobId={selectedJobId} jobName="Unknown Job" />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <FolderOpen className="w-12 h-12 text-slate-400 mx-auto mb-4" />
            <p className="text-slate-500">
              Select a dataset above to explore its structure and files.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default DatasetExplorerPage;
