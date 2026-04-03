import { useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Upload, AlertCircle, CheckCircle2, Loader2, Copy } from 'lucide-react';
import { uploadDatasetToAem, AemUploadConfig } from '@/utils/aemUpload';

export function AemUploadPage() {
  const [jobId, setJobId] = useState('');
  const [aemBaseUrl, setAemBaseUrl] = useState('');
  const [targetPath, setTargetPath] = useState('content/dam/');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [maxConcurrent, setMaxConcurrent] = useState(20);
  const [maxUploadFiles, setMaxUploadFiles] = useState(70000);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    message: string;
    duration?: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopyJobId = useCallback(async () => {
    if (!jobId.trim()) {
      return;
    }

    const jobIdToCopy = jobId.trim();
    
    try {
      // Try modern clipboard API first
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(jobIdToCopy);
        setCopied(true);
        setTimeout(() => {
          setCopied(false);
        }, 2000);
        return;
      }
      
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = jobIdToCopy;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        const successful = document.execCommand('copy');
        if (successful) {
          setCopied(true);
          setTimeout(() => {
            setCopied(false);
          }, 2000);
        } else {
          throw new Error('execCommand copy failed');
        }
      } finally {
        document.body.removeChild(textArea);
      }
    } catch (err) {
      console.error('Failed to copy job ID:', err);
      // Show error feedback
      alert(`Failed to copy job ID. Please copy manually: ${jobIdToCopy}`);
    }
  }, [jobId]);

  const handleUpload = useCallback(async () => {
    if (!jobId.trim()) {
      setError('Please enter a job ID');
      return;
    }

    if (!aemBaseUrl.trim()) {
      setError('Please enter AEM Base URL');
      return;
    }

    if (!targetPath.trim()) {
      setError('Please enter target path');
      return;
    }

    if (!username.trim()) {
      setError('Please enter username');
      return;
    }

    if (!password.trim()) {
      setError('Please enter password');
      return;
    }

    setLoading(true);
    setError(null);
    setUploadResult(null);

    const config: AemUploadConfig = {
      aem_base_url: aemBaseUrl.trim(),
      target_path: targetPath.trim(),
      username: username.trim(),
      password: password.trim(),
      max_concurrent: maxConcurrent,
      max_upload_files: maxUploadFiles,
    };

    try {
      const result = await uploadDatasetToAem(jobId.trim(), config);
      setUploadResult({
        success: result.success,
        message: result.message,
        duration: result.duration,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMessage);
      setUploadResult({
        success: false,
        message: errorMessage,
      });
    } finally {
      setLoading(false);
    }
  }, [jobId, aemBaseUrl, targetPath, username, password, maxConcurrent, maxUploadFiles]);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <div className="text-center py-8 pb-10">
        <h1 className="text-4xl font-bold text-slate-900 mb-3 tracking-tight">
          Upload to AEM
        </h1>
        <p className="text-lg text-slate-600 max-w-2xl mx-auto">
          Upload generated datasets to your AEM instance
        </p>
      </div>

      <Card className="border border-slate-200 shadow-sm hover:shadow-md transition-shadow duration-200">
        <CardHeader className="border-b border-slate-200 pb-4">
          <CardTitle className="text-xl font-semibold text-slate-900 mb-1.5">
            AEM Upload Configuration
          </CardTitle>
          <CardDescription className="text-sm text-slate-600 leading-relaxed">
            Configure your AEM instance details and upload settings
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6 space-y-6">
          <div className="space-y-2">
            <Label htmlFor="jobId" className="text-sm font-semibold text-slate-900">
              Job ID
            </Label>
            <div className="relative">
              <Input
                id="jobId"
                type="text"
                placeholder="Enter job ID"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                disabled={loading}
                className="w-full pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCopyJobId}
                disabled={!jobId.trim() || loading}
                className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 p-0 hover:bg-slate-100 flex items-center justify-center transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                title={copied ? "Copied!" : "Copy Job ID"}
              >
                {copied ? (
                  <CheckCircle2 className="w-4 h-4 text-green-600 animate-fadeIn" />
                ) : (
                  <Copy className="w-4 h-4 text-slate-500 hover:text-slate-700 transition-colors" />
                )}
              </Button>
            </div>
            <p className="text-xs text-slate-500">
              The ID of the completed job whose dataset you want to upload
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="aemBaseUrl" className="text-sm font-semibold text-slate-900">
              AEM Base URL
            </Label>
            <Input
              id="aemBaseUrl"
              type="url"
              placeholder="https://author-p35602-e1337026.adobeaemcloud.com"
              value={aemBaseUrl}
              onChange={(e) => setAemBaseUrl(e.target.value)}
              disabled={loading}
              className="w-full"
            />
            <p className="text-xs text-slate-500">
              Your AEM instance URL (without trailing slash)
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="targetPath" className="text-sm font-semibold text-slate-900">
              Target Path
            </Label>
            <Input
              id="targetPath"
              type="text"
              placeholder="content/dam/Priyanka_Perf/"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              disabled={loading}
              className="w-full"
            />
            <p className="text-xs text-slate-500">
              Target path in AEM where the dataset will be uploaded
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-sm font-semibold text-slate-900">
                Username
              </Label>
              <Input
                id="username"
                type="text"
                placeholder="testadmin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                className="w-full"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-semibold text-slate-900">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                className="w-full"
              />
            </div>
          </div>

          <div className="pt-4 border-t border-slate-200">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              {showAdvanced ? 'Hide' : 'Show'} Advanced Options
            </Button>

            {showAdvanced && (
              <div className="mt-4 space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="maxConcurrent" className="text-sm font-semibold text-slate-900">
                    Max Concurrent Uploads
                  </Label>
                  <Input
                    id="maxConcurrent"
                    type="number"
                    min="1"
                    max="100"
                    value={maxConcurrent}
                    onChange={(e) => setMaxConcurrent(parseInt(e.target.value) || 20)}
                    disabled={loading}
                    className="w-full"
                  />
                  <p className="text-xs text-slate-500">
                    Maximum number of files to upload concurrently (1-100)
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="maxUploadFiles" className="text-sm font-semibold text-slate-900">
                    Max Upload Files
                  </Label>
                  <Input
                    id="maxUploadFiles"
                    type="number"
                    min="1"
                    value={maxUploadFiles}
                    onChange={(e) => setMaxUploadFiles(parseInt(e.target.value) || 70000)}
                    disabled={loading}
                    className="w-full"
                  />
                  <p className="text-xs text-slate-500">
                    Maximum number of files to upload (default: 70000)
                  </p>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-900">Upload Failed</p>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          )}

          {uploadResult && (
            <div
              className={`p-4 border rounded-lg flex items-start gap-3 ${
                uploadResult.success
                  ? 'bg-green-50 border-green-200'
                  : 'bg-red-50 border-red-200'
              }`}
            >
              {uploadResult.success ? (
                <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <p
                  className={`text-sm font-semibold ${
                    uploadResult.success ? 'text-green-900' : 'text-red-900'
                  }`}
                >
                  {uploadResult.success ? 'Upload Successful' : 'Upload Failed'}
                </p>
                <p
                  className={`text-sm mt-1 ${
                    uploadResult.success ? 'text-green-700' : 'text-red-700'
                  }`}
                >
                  {uploadResult.message}
                  {uploadResult.success && uploadResult.duration && (
                    <span className="block mt-1">
                      Completed in {uploadResult.duration.toFixed(2)} seconds
                    </span>
                  )}
                </p>
              </div>
            </div>
          )}

          <div className="pt-4">
            <Button
              onClick={handleUpload}
              disabled={loading || !jobId.trim() || !aemBaseUrl.trim() || !targetPath.trim() || !username.trim() || !password.trim()}
              className="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-blue-400 disabled:cursor-not-allowed text-white font-semibold py-3.5 text-base shadow-md hover:shadow-lg active:shadow-sm transition-all duration-200"
              size="lg"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Uploading...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <Upload className="w-4 h-4" />
                  Upload to AEM
                </span>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default AemUploadPage;
