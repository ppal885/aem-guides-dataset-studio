import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Upload, FileText, Sparkles, Loader2 } from 'lucide-react';

interface BulkJobCreatorProps {
  onJobsCreated: (jobIds: string[]) => void;
}

export function BulkJobCreator({ onJobsCreated }: BulkJobCreatorProps) {
  const [loading, setLoading] = useState(false);
  const [namePrefix, setNamePrefix] = useState('');
  const [jobCount, setJobCount] = useState(1);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleCreateFromCount = useCallback(async () => {
    if (jobCount < 1 || jobCount > 100) {
      setError('Job count must be between 1 and 100');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const jobs = Array.from({ length: jobCount }, (_, index) => ({
        config: {
          name: namePrefix ? `${namePrefix} - Job ${index + 1}` : `Bulk Job ${index + 1}`,
          seed: `bulk-${Date.now()}-${index}`,
          root_folder: '/content/dam/dataset-studio',
          windows_safe_filenames: true,
          doctype_topic: '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
          doctype_reference:
            '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">',
          doctype_map: '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
          doctype_bookmap:
            '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">',
          doctype_glossentry:
            '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossentry//EN" "technicalContent/dtd/glossentry.dtd">',
          recipes: [{
            type: 'task_topics',
            topic_count: 10,
            steps_per_task: 5,
            include_prereq: true,
            include_result: true,
            include_map: true,
            pretty_print: true,
          }],
        },
      }));

      const response = await fetch('/api/v1/bulk/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jobs,
          name_prefix: namePrefix || undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to create bulk jobs' }));
        throw new Error(errorData.detail || 'Failed to create bulk jobs');
      }

      const result = await response.json();
      setSuccess(`Successfully created ${result.created} job(s)`);
      if (result.job_ids && result.job_ids.length > 0) {
        onJobsCreated(result.job_ids);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create bulk jobs');
    } finally {
      setLoading(false);
    }
  }, [jobCount, namePrefix, onJobsCreated]);

  const handleCsvUpload = useCallback(async () => {
    if (!csvFile) {
      setError('Please select a CSV file');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const text = await csvFile.text();
      const lines = text.split('\n').filter(line => line.trim());
      
      if (lines.length < 2) {
        throw new Error('CSV must have at least a header row and one data row');
      }

      const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
      const requiredHeaders = ['name', 'seed', 'recipe_type'];
      const missingHeaders = requiredHeaders.filter(h => !headers.includes(h));
      
      if (missingHeaders.length > 0) {
        throw new Error(`CSV missing required columns: ${missingHeaders.join(', ')}`);
      }

      const jobs = lines.slice(1).map((line, index) => {
        const values = line.split(',').map(v => v.trim());
        const row: Record<string, string> = {};
        headers.forEach((header, idx) => {
          row[header] = values[idx] || '';
        });

        const jobName = namePrefix ? `${namePrefix} - ${row.name}` : row.name;
        
        const baseConfig: Record<string, any> = {
          name: jobName,
          seed: row.seed || `csv-${Date.now()}-${index}`,
          root_folder: row.root_folder || '/content/dam/dataset-studio',
          windows_safe_filenames: true,
          doctype_topic: '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
          doctype_reference:
            '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">',
          doctype_map: '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
          doctype_bookmap:
            '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">',
          doctype_glossentry:
            '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossentry//EN" "technicalContent/dtd/glossentry.dtd">',
        };

        const recipeType = row.recipe_type || 'task_topics';
        const recipeConfig: Record<string, any> = {
          type: recipeType,
          topic_count: parseInt(row.topic_count) || 10,
          include_map: true,
          pretty_print: true,
        };

        if (recipeType === 'task_topics') {
          recipeConfig.steps_per_task = parseInt(row.steps_per_task) || 5;
          recipeConfig.include_prereq = true;
          recipeConfig.include_result = true;
        }

        baseConfig.recipes = [recipeConfig];

        return { config: baseConfig };
      });

      if (jobs.length === 0) {
        throw new Error('No valid jobs found in CSV');
      }

      if (jobs.length > 100) {
        throw new Error('CSV contains more than 100 jobs. Maximum is 100.');
      }

      const response = await fetch('/api/v1/bulk/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jobs,
          name_prefix: namePrefix || undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to create bulk jobs' }));
        throw new Error(errorData.detail || 'Failed to create bulk jobs');
      }

      const result = await response.json();
      setSuccess(`Successfully created ${result.created} job(s) from CSV`);
      if (result.job_ids && result.job_ids.length > 0) {
        onJobsCreated(result.job_ids);
      }
      setCsvFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process CSV file');
    } finally {
      setLoading(false);
    }
  }, [csvFile, namePrefix, onJobsCreated]);

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div>
          <Label htmlFor="name-prefix">Name Prefix (Optional)</Label>
          <Input
            id="name-prefix"
            value={namePrefix}
            onChange={(e) => setNamePrefix(e.target.value)}
            placeholder="e.g., Test Run 2024"
            className="mt-1"
          />
          <p className="text-xs text-slate-500 mt-1">
            This prefix will be added to all job names
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              Create Multiple Jobs
            </CardTitle>
            <CardDescription>
              Create multiple jobs with the same recipe configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="job-count">Number of Jobs</Label>
              <Input
                id="job-count"
                type="number"
                min="1"
                max="100"
                value={jobCount}
                onChange={(e) => setJobCount(parseInt(e.target.value) || 1)}
                className="mt-1"
              />
              <p className="text-xs text-slate-500 mt-1">
                Maximum 100 jobs per request
              </p>
            </div>
            <Button
              onClick={handleCreateFromCount}
              disabled={loading || jobCount < 1 || jobCount > 100}
              className="w-full"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 mr-2" />
                  Create {jobCount} Job{jobCount !== 1 ? 's' : ''}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Import from CSV
            </CardTitle>
            <CardDescription>
              Upload a CSV file to create jobs with different configurations
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="csv-file">CSV File</Label>
              <div className="mt-1 flex items-center gap-2">
                <Input
                  id="csv-file"
                  type="file"
                  accept=".csv"
                  onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                  className="flex-1"
                />
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Required columns: name, seed, recipe_type
              </p>
              <p className="text-xs text-slate-500">
                Optional columns: root_folder, topic_count, steps_per_task
              </p>
            </div>
            <Button
              onClick={handleCsvUpload}
              disabled={loading || !csvFile}
              className="w-full"
              variant="outline"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2" />
                  Upload & Create Jobs
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {success && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">{success}</p>
        </div>
      )}
    </div>
  );
}
